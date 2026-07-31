/* ============================================================================
 * Mastermind Brain — the unified chat widget (dashboard + Terminal).
 *
 * Self-contained: injects its own CSS + DOM, wires the live /api/brain/* gateway
 * (Bearer auth via MDXAuth, SSE stream, threads, quota, Fast/Pro lanes, Deep
 * Research, inline charts), and renders an intercom launcher that opens to a
 * compact chatbox and expands to a centred ~80% overlay.
 *
 * Config (optional, set window.MM_BRAIN_CFG before this script):
 *   anchor: 'br'  (bottom-right launcher — dashboard, default)
 *         | 'top' (host provides its own launcher; call MMBrain.open())
 *   api:    gateway base (default '' = same origin)
 *   symbol: fn()->active ticker string (context awareness)
 *   page:   context label (default derived from location)
 * Public API: window.MMBrain = { open, close, toggle, expand, mounted:true }
 * ========================================================================== */
(function () {
  'use strict';
  if (window.MMBrain && window.MMBrain.mounted) return;
  var CFG = window.MM_BRAIN_CFG || {};
  var ANCHOR = CFG.anchor || 'br';
  var API = (CFG.api || '').replace(/\/$/, '');
  var DOC = document;

  /* ── i18n mini-helper (mirrors the site l-en/l-zh idiom) ── */
  function zh() { return DOC.documentElement.getAttribute('data-lang') === 'zh'; }
  function L(en, cn) { return zh() ? cn : en; }
  /* re-localizable label — carries BOTH languages so a live switch can re-tint it
     in place (see relabel()); use for chrome text that persists across renders. */
  function LB(en, cn) { return '<span class="mmb-l" data-en="' + en + '" data-zh="' + cn + '">' + L(en, cn) + '</span>'; }
  /* Stream events carry their OWN bilingual label pair (status/tool). Fall back to the
     house line when the server sends none (an older gateway) — never to an internal
     tool name, which is not user language and not ours to show. */
  function evLabel(j, en, cn) { return L(j.label_en || en, j.label_zh || cn); }
  /* Optional qualifier on an event (a server-sanitized symbol) — trimmed and capped. */
  function evDetail(j) { return j.detail ? String(j.detail).trim().slice(0, 24) : ''; }

  /* ── send shortcut ───────────────────────────────────────────────────────────
     Enter writes a new line (the composer is a multi-line box first, operator order);
     sending is ⌘/Ctrl+Enter, Shift+Enter, or the button. Spell the modifier the way the
     user's own keyboard spells it — ⌘ on Apple hardware, Ctrl everywhere else. */
  var SEND_KEYS = (function () {
    try { return /Mac|iPhone|iPad|iPod/.test(navigator.platform || navigator.userAgent || '') ? '⌘↵' : 'Ctrl+↵'; }
    catch (e) { return 'Ctrl+↵'; }
  })();


  /* ── CSS ─────────────────────────────────────────────────────────────── */
  var CSS = `
  /* ── palette ───────────────────────────────────────────────────────────────
     The widget follows the host page's theme (html[data-theme]) — no JS, no
     re-render: every surface, border and hover reads a token, so flipping the
     site switch repaints the chat mid-conversation.

     Two direction tokens do the heavy lifting, because "lighter" is not a
     theme-independent idea:
       --mmb-ink  the ELEVATION direction. Every raised surface / hairline /
                  hover is color-mix(ink N%, transparent) — white over the dark
                  panel, slate over the white one.
       --mmb-hi   the EMPHASIS direction for text ranked above --mmb-text
                  (bold, headings, code). White in dark, near-black in light. */
  #mmb-root{--mmb-info:#5b9bf0;--mmb-violet:#8b5cf6;--mmb-text:#e6eaf0;--mmb-muted:#8b93a1;
    --mmb-panel:#181b21;--mmb-panel2:#1e222a;
    --mmb-ink:#fff;--mmb-hi:#fff;--mmb-line:color-mix(in srgb,var(--mmb-ink) 9%,transparent);
    --mmb-sheen:color-mix(in srgb,#fff 6%,transparent);
    --mmb-well:color-mix(in srgb,#000 22%,transparent);
    --mmb-plate:#0b0e14;--mmb-glow:#5b7bf0;
    --mmb-card:color-mix(in srgb,var(--mmb-panel) 50%,transparent);
    --mmb-boxbg:color-mix(in srgb,var(--mmb-panel2) 60%,transparent);
    --mmb-exp-fg:#fff;--mmb-exp-bg:color-mix(in srgb,var(--mmb-panel) 72%,transparent);--mmb-exp-shadow:none;
    --mmb-ok:#3da564;--mmb-warn:#e0a030;--mmb-danger:#e05555;--mmb-danger-soft:#e0716b;--mmb-step-o:.68;
    --mmb-scrim:#05070c;--mmb-scrim-o:.34;--mmb-scrim-o-max:.62;--mmb-sidescrim:rgba(0,0,0,.32);
    --mmb-shadow-panel:0 40px 100px -30px rgba(0,0,0,.75);
    --mmb-shadow-box:0 14px 40px -18px rgba(0,0,0,.6);
    --mmb-shadow-pop:0 10px 30px -12px rgba(0,0,0,.6);
    --mmb-shadow-side:10px 0 40px -12px rgba(0,0,0,.6);
    /* launcher — see the presence note at #mmb-launch */
    --mmb-fab-bg:color-mix(in srgb,var(--mmb-panel) 82%,transparent);
    --mmb-fab-brd:var(--mmb-line);
    --mmb-fab-glow:0 12px 40px -12px rgba(0,0,0,.6),
      0 0 26px -8px color-mix(in srgb,var(--mmb-info) 40%,transparent),
      0 0 0 1px color-mix(in srgb,var(--mmb-info) 12%,transparent);
    --mmb-fab-glow-h:0 18px 52px -14px rgba(0,0,0,.7),
      0 0 36px -8px color-mix(in srgb,var(--mmb-info) 60%,transparent),
      0 0 0 1px color-mix(in srgb,var(--mmb-info) 26%,transparent);
    --mmb-rim-w:1.25px;--mmb-rim-o:.85;
    --mmb-font:Inter,-apple-system,"Segoe UI",Roboto,sans-serif;
    /* Motion tokens. ONE deceleration curve for everything that travels (long tail —
       things arrive and settle rather than stop), one faster curve for state tints that
       must feel instant. Named here so a hover, a landing ledger row and the panel morph
       are visibly the same hand; MORPH_EASE in JS is the same curve. */
    --mmb-ease:cubic-bezier(.22,1,.36,1);--mmb-ease-tint:cubic-bezier(.3,.8,.4,1);
    --mmb-mono:ui-monospace,SFMono-Regular,Menlo,monospace}
  /* Light theme. The house light palette (theme.css) verbatim, so the chat is the
     same design family as the page behind it: #285fff primary, white panels on a
     soft #eef1f6 grid, navy-tinted shadows instead of black ones. */
  html[data-theme="light"] #mmb-root{
    --mmb-info:#285fff;--mmb-violet:#6d3fd8;--mmb-text:#1c2430;--mmb-muted:#5d6b7e;
    --mmb-panel:#ffffff;--mmb-panel2:#eef1f6;
    /* hairlines run a few points heavier than the dark theme's: dark-on-light reads
       weaker than light-on-dark at the same alpha, and these are the only thing
       separating a white rail from a white pane. */
    --mmb-ink:#1c2430;--mmb-hi:#080d16;--mmb-line:color-mix(in srgb,var(--mmb-ink) 14%,transparent);
    --mmb-sheen:rgba(255,255,255,.9);
    --mmb-well:color-mix(in srgb,var(--mmb-ink) 6%,transparent);
    --mmb-plate:#e7ebf2;--mmb-glow:#285fff;
    --mmb-card:color-mix(in srgb,var(--mmb-panel2) 62%,transparent);
    --mmb-boxbg:color-mix(in srgb,var(--mmb-panel2) 80%,transparent);
    /* the explain-panel dot rides ON a white card, so 72% white is nothing to see:
       in light it earns its edge from a near-opaque fill plus a soft lift. */
    --mmb-exp-fg:#4b34c9;--mmb-exp-bg:rgba(255,255,255,.94);
    --mmb-exp-shadow:0 4px 12px -4px rgba(20,32,64,.26);
    --mmb-ok:#2f8a52;--mmb-warn:#b9791a;--mmb-danger:#cf4040;--mmb-danger-soft:#c12f2f;--mmb-step-o:.82;
    /* a light-mode veil is a cool navy at low alpha — pure black reads as a power cut */
    --mmb-scrim:#1b2436;--mmb-scrim-o:.22;--mmb-scrim-o-max:.44;--mmb-sidescrim:rgba(20,30,50,.20);
    --mmb-shadow-panel:0 34px 84px -28px rgba(20,32,64,.34),0 12px 30px -16px rgba(20,32,64,.18);
    --mmb-shadow-box:0 12px 30px -16px rgba(20,32,64,.20);
    --mmb-shadow-pop:0 12px 30px -14px rgba(20,32,64,.26);
    --mmb-shadow-side:12px 0 34px -14px rgba(20,32,64,.20);
    /* White on white is the whole problem here: the chip keeps a faint blue floor so it
       never dissolves into a white card, and its glow is a navy lift rather than the
       dark theme's black drop, which would read as grime over a light page. */
    --mmb-fab-bg:linear-gradient(180deg,rgba(255,255,255,.97),
      color-mix(in srgb,var(--mmb-info) 11%,rgba(255,255,255,.9)));
    --mmb-fab-brd:color-mix(in srgb,var(--mmb-info) 24%,transparent);
    --mmb-fab-glow:0 14px 34px -14px rgba(24,52,140,.40),0 6px 16px -8px rgba(24,52,140,.26),
      0 0 24px -6px color-mix(in srgb,var(--mmb-info) 38%,transparent),inset 0 1px 0 #fff;
    --mmb-fab-glow-h:0 20px 46px -14px rgba(24,52,140,.48),0 8px 20px -8px rgba(24,52,140,.32),
      0 0 36px -6px color-mix(in srgb,var(--mmb-info) 56%,transparent),inset 0 1px 0 #fff;
    --mmb-rim-w:1.75px;--mmb-rim-o:1}
  #mmb-root *{box-sizing:border-box}
  /* ── launcher (bottom-right) ────────────────────────────────────────────────
     Presence is this control's whole job, and a glass pill dissolves on a white
     canvas — so the launcher carries two devices, one still and one moving:

       · a themed drop-glow (blue-tinted over light, near-black over dark), and
       · one chromatic arc that travels the rim every 5.2s — the desk sweeping
         the tape it is offering to read.

     Motion rather than a brightness pulse: a travelling edge catches the eye at
     the corner of vision without nagging, and it survives on white, where a
     pulsing white glow has nothing to pulse against. Hover shortens the sweep
     to 2.4s — the chip acknowledges you before you click it. */
  @property --mmb-ang{syntax:'<angle>';initial-value:0deg;inherits:false}
  @keyframes mmb-rim{to{--mmb-ang:360deg}}
  #mmb-launch{position:fixed;right:22px;bottom:22px;z-index:2147483000;display:flex;align-items:center;gap:10px;
    padding:8px 16px 8px 8px;border-radius:999px;cursor:pointer;border:1px solid var(--mmb-fab-brd);font-family:var(--mmb-font);
    background:var(--mmb-fab-bg);-webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px);
    box-shadow:var(--mmb-fab-glow);
    transition:transform .18s ease,box-shadow .18s ease}
  #mmb-launch:hover{transform:translateY(-2px);box-shadow:var(--mmb-fab-glow-h)}
  /* visibility, not just opacity: a launcher hidden behind the open panel is still a tab
     stop if it only fades, so a keyboard user would tab onto an invisible pill. */
  #mmb-launch.mmb-hide{opacity:0;pointer-events:none;visibility:hidden;transform:translateY(8px)}
  /* The arc is a conic gradient masked down to the rim band. Gated on
     mask-composite: where the mask cannot be composited the ring would paint as a
     full coloured disc over the pill, so it is better to have no ring at all —
     the glow and the breathing orb still carry the control. */
  @supports ((-webkit-mask-composite:xor) or (mask-composite:exclude)){
    #mmb-launch::before{content:'';position:absolute;inset:-1px;border-radius:inherit;pointer-events:none;
      padding:var(--mmb-rim-w);opacity:var(--mmb-rim-o);
      background:conic-gradient(from var(--mmb-ang),transparent 0 46%,
        var(--mmb-violet) 66%,var(--mmb-info) 82%,transparent 92%);
      -webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);
      -webkit-mask-composite:xor;
      mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);mask-composite:exclude;
      animation:mmb-rim 5.2s linear infinite}
    #mmb-launch:hover::before{animation-duration:2.4s;opacity:1}
  }
  /* The launcher is the one control that floats over ARBITRARY page content, so its focus
     ring cannot borrow a known backdrop the way the in-panel rings borrow the dark panel —
     and the themed pill is near-white in light and near-black in dark, so it cannot lean on
     the pill either. Three concentric tones drawn outward: house blue hugging the pill, then
     a white hairline, then a dark edge. The achromatic pair is what survives BOTH themes;
     the blue is what makes it read as this desk's focus ring rather than the UA default.
     ::after because the rim arc above already owns ::before. */
  #mmb-launch:focus-visible{outline:2px solid var(--mmb-info);outline-offset:2px}
  #mmb-launch:focus-visible::after{content:'';position:absolute;inset:-4px;border-radius:inherit;pointer-events:none;
    box-shadow:0 0 0 1.5px rgba(255,255,255,.92),0 0 0 3px rgba(6,10,20,.55)}
  .mmb-orb{width:38px;height:38px;border-radius:50%;flex:none;display:grid;place-items:center;position:relative;
    background:radial-gradient(circle at 32% 28%,color-mix(in srgb,#a78bfa 92%,#fff),#416aec 60%,#0b1030 100%);
    box-shadow:inset 0 1px 3px color-mix(in srgb,#fff 45%,transparent),0 0 18px -2px color-mix(in srgb,var(--mmb-glow) 80%,transparent);
    animation:mmb-breathe 4.6s ease-in-out infinite}
  .mmb-orb::after{content:'';position:absolute;inset:-6px;border-radius:50%;z-index:-1;
    background:radial-gradient(circle,color-mix(in srgb,#6b8cf0 34%,transparent),transparent 70%);animation:mmb-breathe 4.6s ease-in-out infinite}
  .mmb-orb svg{width:19px;height:19px;fill:#fff;opacity:.96;filter:drop-shadow(0 1px 2px rgba(0,0,0,.4))}
  @keyframes mmb-breathe{0%,100%{transform:scale(1);opacity:.96}50%{transform:scale(1.07);opacity:1}}
  /* Sidebar + rail resolve in a beat after the morph settles, so they arrive rather than
     stretch out of the scaling frame. */
  @keyframes mmb-morph-in{from{opacity:0;transform:translateX(-10px)}to{opacity:1;transform:none}}
  #mmb-panel.max .mmb-rail{animation:mmb-morph-in .44s .14s both cubic-bezier(.22,1,.36,1)}
  #mmb-panel.max .mmb-threads{animation:mmb-morph-in .5s .2s both cubic-bezier(.22,1,.36,1)}
  /* reduced motion: the rim parks at its start angle — still a chromatic edge, so the
     launcher keeps its presence without anything moving. */
  /* Every animation this file starts is named here, PSEUDOS INCLUDED — a kill block that
     lists only the element leaves its ::before/::after spinning, which is exactly the
     motion a reduced-motion user asked not to see. */
  @media(prefers-reduced-motion:reduce){.mmb-orb,.mmb-orb::after,
    #mmb-launch::before,#mmb-launch:hover::before,
    #mmb-panel.max .mmb-rail,#mmb-panel.max .mmb-threads,
    .mmb-tk-row,.mmb-tk-h .lb.mmb-swap,.mmb-tk-h .mmb-tk-ic::after,
    .mmb-recap.on .mmb-recap-list,.mmb-cards .mmb-cardp,.mmb-hero h1,.mmb-hero p,
    .mmb-sugg .mmb-sug,.mmb-rpill.on svg .dv{animation:none}
    #mmb-panel{transition:opacity .18s ease!important}
    .mmb-chip,.mmb-chip::after,.mmb-cardp,.mmb-cardp .ci svg,.mmb-seg button,.mmb-rpill,
    .mmb-rtip,.mmb-send,.mmb-box,.mmb-sug,.mmb-tbtn{transition:none}
    /* the tip still appears, it just does not travel */
    .mmb-rtip{transform:none}}
  #mmb-launch .ll{font:650 13.5px/1 var(--mmb-font);color:var(--mmb-text);white-space:nowrap}
  #mmb-launch .lk{font:600 11px/1 var(--mmb-font);color:var(--mmb-muted);margin-top:3px;white-space:nowrap}
  #mmb-launch .lt{display:flex;flex-direction:column}
  /* phones: collapse the labelled pill down to the lone orb — the label is desktop
     affordance and the full pill crowds small screens. */
  @media(max-width:700px){
    #mmb-launch{right:16px;bottom:calc(16px + env(safe-area-inset-bottom,0px));padding:8px;gap:0}
    #mmb-launch .lt{display:none}
  }
  /* scrim + panel */
  /* Backdrop deepens as you enter focus mode: a light veil behind the compact chatbox,
     full dim behind the expanded overlay. */
  #mmb-scrim{position:fixed;inset:0;z-index:2147483001;background:var(--mmb-scrim);
    -webkit-backdrop-filter:blur(2px);backdrop-filter:blur(2px);opacity:0;pointer-events:none;
    transition:opacity .5s cubic-bezier(.22,1,.36,1),backdrop-filter .5s ease,-webkit-backdrop-filter .5s ease}
  #mmb-scrim.open{opacity:var(--mmb-scrim-o);pointer-events:auto}
  #mmb-scrim.open.max{opacity:var(--mmb-scrim-o-max);-webkit-backdrop-filter:blur(5px);backdrop-filter:blur(5px)}
  #mmb-panel{position:fixed;z-index:2147483002;display:flex;flex-direction:column;overflow:hidden;font-family:var(--mmb-font);color:var(--mmb-text);
    right:18px;bottom:18px;width:min(440px,calc(100vw - 36px));height:min(720px,calc(100vh - 96px));
    border-radius:22px;border:1px solid var(--mmb-line);background:color-mix(in srgb,var(--mmb-panel) 82%,transparent);
    -webkit-backdrop-filter:blur(26px) saturate(1.15);backdrop-filter:blur(26px) saturate(1.15);
    box-shadow:var(--mmb-shadow-panel),inset 0 1px 0 var(--mmb-sheen);
    transform:translateY(16px) scale(.98);opacity:0;pointer-events:none;visibility:hidden;transform-origin:bottom right;
    /* CSS owns OPACITY only. TRANSFORM is driven entirely by the Web Animations API (entry
       + the compact↔max morph) so nothing ever transitions transform in CSS — a CSS transform
       transition would fight the WAAPI morph and freeze it at the inverted start.
       VISIBILITY is what keeps a CLOSED panel out of the tab order: opacity:0 alone leaves
       every control inside it focusable, so tabbing through any page on the site walked
       into ~23 invisible chat controls. Delayed 0s step AFTER the fade, so closing still
       reads as a fade-out and not a cut. */
    transition:opacity .26s ease,visibility 0s linear .26s}
  #mmb-panel.mmb-top{right:18px;top:64px;bottom:auto;transform-origin:top right;transform:translateY(-16px) scale(.98)}
  #mmb-panel.open{transform:none;opacity:1;pointer-events:auto;visibility:visible;transition:opacity .26s ease,visibility 0s}
  /* Transform-free centering (inset:0 + margin:auto) so the panel's resting transform is
     'none' in BOTH states — the FLIP invert composes cleanly against it. */
  #mmb-panel.max{inset:0;margin:auto;width:min(1480px,90vw);height:min(1240px,95vh)}
  .mmb-body{display:flex;flex:1;min-height:0}
  .mmb-rail{width:52px;flex:none;display:flex;flex-direction:column;align-items:center;gap:6px;padding:14px 0;border-right:1px solid color-mix(in srgb,var(--mmb-line) 55%,transparent)}
  .mmb-rail .logo{width:30px;height:30px;border-radius:9px;background:linear-gradient(145deg,var(--mmb-glow),var(--mmb-violet));display:grid;place-items:center;margin-bottom:8px}
  .mmb-rail .logo svg{width:16px;height:16px;fill:#fff}
  .mmb-icon{width:34px;height:34px;border:none;background:transparent;border-radius:10px;color:var(--mmb-muted);cursor:pointer;display:grid;place-items:center;transition:background .13s,color .13s}
  .mmb-icon:hover{background:color-mix(in srgb,var(--mmb-ink) 7%,transparent);color:var(--mmb-text)}
  .mmb-icon svg{width:18px;height:18px;stroke:currentColor;fill:none;stroke-width:1.8}
  .mmb-rail .sp{flex:1}
  .mmb-threads{width:0;flex:none;overflow:hidden auto;border-right:1px solid color-mix(in srgb,var(--mmb-line) 55%,transparent);transition:width .26s ease}
  #mmb-panel.max .mmb-threads{width:236px}
  /* Scoped to the rail on purpose. A bare .mmb-th-h span rule is uppercase + letterspaced
     with no owner, and it silently ate the reasoning ledger's label the first time a second
     header in this file wanted a similar name. */
  .mmb-threads .mmb-th-h{display:flex;align-items:center;justify-content:space-between;padding:16px 16px 10px}
  .mmb-threads .mmb-th-h span{font:700 11px/1 var(--mmb-font);letter-spacing:.08em;text-transform:uppercase;color:var(--mmb-muted)}
  .mmb-search{display:none;align-items:center;gap:8px;margin:2px 10px 8px;padding:7px 10px;border-radius:10px;background:color-mix(in srgb,var(--mmb-ink) 5%,transparent);border:1px solid var(--mmb-line)}
  .mmb-search.on{display:flex}
  .mmb-search>svg{width:15px;height:15px;stroke:var(--mmb-muted);fill:none;stroke-width:1.8;flex:none}
  .mmb-search input{flex:1;min-width:0;border:none;background:none;outline:none;color:var(--mmb-text);font:13px/1.2 var(--mmb-font)}
  .mmb-search input::placeholder{color:var(--mmb-muted)}
  .mmb-search .x{border:none;background:none;cursor:pointer;color:var(--mmb-muted);display:grid;place-items:center;padding:2px;border-radius:6px;flex:none;transition:color .12s,opacity .12s}
  .mmb-search .x:hover{color:var(--mmb-text)}
  .mmb-search .x svg{width:13px;height:13px;stroke:currentColor;fill:none;stroke-width:2}
  .mmb-search input:placeholder-shown~.x{opacity:0;pointer-events:none}
  .mmb-ti{position:relative;display:flex;align-items:center;margin:2px 8px;padding:9px 11px;border-radius:10px;cursor:pointer;border:1px solid transparent}
  .mmb-ti:hover{background:color-mix(in srgb,var(--mmb-ink) 6%,transparent)}
  .mmb-ti.on{background:color-mix(in srgb,var(--mmb-info) 14%,transparent);border-color:color-mix(in srgb,var(--mmb-info) 30%,transparent)}
  .mmb-ti-body{flex:1;min-width:0}
  .mmb-ti .tt{font:600 13px/1.3 var(--mmb-font);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .mmb-ti .tm{font:500 11px/1 var(--mmb-font);color:var(--mmb-muted);margin-top:3px;text-transform:capitalize;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  /* row action buttons (rename/delete) — reveal on hover; always 0.7 on coarse */
  .mmb-ti-acts{display:flex;gap:2px;flex:none;margin-left:6px;opacity:0;transition:opacity .13s}
  .mmb-ti:hover .mmb-ti-acts,.mmb-ti:focus-within .mmb-ti-acts{opacity:1}
  @media(hover:none),(pointer:coarse){.mmb-ti-acts{opacity:.7}}
  .mmb-ti.confirming .mmb-ti-acts{display:none}
  .mmb-ti-act{width:22px;height:22px;border:none;background:transparent;border-radius:6px;color:var(--mmb-muted);cursor:pointer;display:grid;place-items:center;padding:0;transition:color .12s,background .12s}
  .mmb-ti-act:hover{color:var(--mmb-text);background:color-mix(in srgb,var(--mmb-ink) 9%,transparent)}
  .mmb-ti-act svg{width:14px;height:14px;stroke:currentColor;fill:none;stroke-width:1.7}
  /* inline rename input (replaces the title in place) */
  .mmb-ti-input{width:100%;border:1px solid color-mix(in srgb,var(--mmb-info) 40%,transparent);background:var(--mmb-well);color:var(--mmb-text);font:600 13px/1.3 var(--mmb-font);border-radius:7px;padding:4px 7px;outline:none}
  /* delete-confirm state: dim title, show Delete? + ✓/✕ */
  .mmb-ti.confirming .mmb-ti-body{opacity:.4}
  .mmb-ti-confirm{display:none;align-items:center;gap:4px;flex:none;margin-left:6px}
  .mmb-ti.confirming .mmb-ti-confirm{display:flex}
  .mmb-ti-q{font:600 11.5px/1 var(--mmb-font);color:var(--mmb-danger-soft);margin-right:2px}
  .mmb-ti-yes,.mmb-ti-no{width:22px;height:22px;border:none;border-radius:6px;cursor:pointer;display:grid;place-items:center;padding:0;background:color-mix(in srgb,var(--mmb-ink) 6%,transparent);transition:background .12s,color .12s}
  .mmb-ti-yes{color:var(--mmb-danger-soft)}.mmb-ti-yes:hover{background:color-mix(in srgb,var(--mmb-danger) 22%,transparent);color:#fff}
  .mmb-ti-no{color:var(--mmb-muted)}.mmb-ti-no:hover{background:color-mix(in srgb,var(--mmb-ink) 12%,transparent);color:var(--mmb-text)}
  .mmb-ti-yes svg,.mmb-ti-no svg{width:13px;height:13px;stroke:currentColor;fill:none;stroke-width:2.2}
  .mmb-th-empty{color:var(--mmb-muted);font:400 12.5px/1.5 var(--mmb-font);padding:14px 16px}
  .mmb-main{flex:1;display:flex;flex-direction:column;min-width:0}
  .mmb-head{display:flex;align-items:center;gap:8px;padding:14px 14px;flex:none;border-bottom:1px solid color-mix(in srgb,var(--mmb-line) 45%,transparent)}
  /* tight-width discipline: pills/buttons never wrap or shrink — the TITLE gives way (ellipsis) */
  .mmb-head .ttl{font:650 14px/1 var(--mmb-font);display:flex;align-items:center;gap:8px;min-width:0}
  .mmb-head .ttl .mmb-l{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .mmb-head .mmb-icon{flex:none}
  .mmb-head .dot{flex:none;width:7px;height:7px;border-radius:50%;background:var(--mmb-ok);box-shadow:0 0 8px var(--mmb-ok);transition:background .2s}
  /* streaming: violet + soft opacity pulse (opacity-only, house perf law) */
  .mmb-head .dot.busy{background:var(--mmb-violet);box-shadow:0 0 8px var(--mmb-violet);animation:mmb-dotpulse 1s ease-in-out infinite}
  @keyframes mmb-dotpulse{0%,100%{opacity:1}50%{opacity:.45}}
  @media(prefers-reduced-motion:reduce){.mmb-head .dot.busy{animation:none}}
  .mmb-head .sp{flex:1}
  /* Deep Research is the third stop on the depth control, not a separate mode: the
     gateway forces lane='pro' for mode='research', so arming it lights Pro too. That
     pair is the point — Pro in the signature blue says which bucket is being spent,
     Deep in violet says this is a longer pass on top of it. Violet is already this
     widget's "in flight / going deeper" accent (the caret, the busy dot, the ledger's
     live arc), so the two lit stops read as one sentence rather than as a contradiction.
     At REST it stays inert like its neighbours — the standing violet tint that used to
     read as "already on" with Fast selected is a state setLane/setResearch make
     impossible, and it is not coming back through the hover either. */
  .mmb-rpill{position:relative;display:inline-flex;align-items:center;gap:5px;font:600 11.5px/1 var(--mmb-font);cursor:pointer;white-space:nowrap;flex:none;
    color:var(--mmb-muted);background:transparent;border:none;border-radius:999px;padding:5px 11px 5px 9px;
    transition:color .16s var(--mmb-ease-tint),background .16s var(--mmb-ease-tint),box-shadow .16s var(--mmb-ease-tint)}
  .mmb-rpill svg{width:13px;height:13px;stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;flex:none}
  .mmb-rpill:hover{color:color-mix(in srgb,var(--mmb-text) 80%,var(--mmb-muted));background:color-mix(in srgb,var(--mmb-ink) 7%,transparent)}
  .mmb-rpill.on,.mmb-rpill.on:hover{background:linear-gradient(180deg,color-mix(in srgb,var(--mmb-violet) 88%,#fff),var(--mmb-violet));
    color:#fff;box-shadow:0 2px 10px -3px color-mix(in srgb,var(--mmb-violet) 70%,transparent)}
  .mmb-rpill:focus-visible{outline:2px solid color-mix(in srgb,var(--mmb-info) 70%,transparent);outline-offset:2px}
  /* a hairline before the third stop: Fast/Pro are alternatives to each other, Deep is a
     step past both — the divider says so without a second control */
  .mmb-rpill::before{content:'';position:absolute;left:-1px;top:5px;bottom:5px;width:1px;
    background:color-mix(in srgb,var(--mmb-ink) 12%,transparent)}
  .mmb-rpill.on::before,.mmb-rpill:hover::before{opacity:0}
  /* phones: the label gives way to the mark alone (aria-label carries the name) */
  @media(max-width:560px){.mmb-rpill .mmb-l{display:none}.mmb-rpill{padding:5px 8px}}
  /* Arming it plays the mark's own meaning once: the two chevrons travel down through
     the rule they sit under. One 520ms gesture on a deliberate click, never a loop. */
  .mmb-rpill.on svg .dv{animation:mmb-dive .52s var(--mmb-ease) both}
  @keyframes mmb-dive{0%{transform:translateY(-3px);opacity:.25}100%{transform:none;opacity:1}}
  .mmb-rpill.mmb-off{display:none}
  /* What the toggle actually changes, in plain words — the doctrine's Tier-2 home for
     mechanics. It opens UPWARD: the control sits on the composer, so a tip below it would
     land off the panel; and left-anchored rather than centred, because the third stop is
     near the panel's left edge in the compact box. */
  .mmb-rtip{position:absolute;bottom:calc(100% + 10px);left:-6px;transform:translateY(4px);z-index:12;width:min(258px,68vw);white-space:normal;
    pointer-events:none;opacity:0;visibility:hidden;text-align:left;
    font:400 11.5px/1.55 var(--mmb-font);color:var(--mmb-text);
    background:color-mix(in srgb,var(--mmb-panel) 96%,transparent);-webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px);
    border:1px solid var(--mmb-line);border-radius:12px;padding:10px 12px;box-shadow:var(--mmb-shadow-pop);
    transition:opacity .18s var(--mmb-ease),transform .18s var(--mmb-ease),visibility 0s linear .18s}
  .mmb-rpill:hover .mmb-rtip,.mmb-rpill:focus-visible .mmb-rtip{opacity:1;visibility:visible;transform:none;transition-delay:0s,0s,0s}
  .mmb-rtip b{display:block;font:700 11.5px/1.4 var(--mmb-font);color:color-mix(in srgb,var(--mmb-text) 96%,var(--mmb-hi));margin-bottom:3px}
  .mmb-rtip .cost{display:block;margin-top:5px;color:var(--mmb-muted)}
  @media(max-width:560px){.mmb-rtip{display:none}}
  #mmb-panel.max .mmb-menu,#mmb-panel.max .mmb-sidescrim{display:none}
  #mmb-panel:not(.max) .mmb-rail{display:none}
  #mmb-panel:not(.max) .mmb-threads{position:absolute;left:0;top:0;bottom:0;width:236px;z-index:6;display:block;
    background:color-mix(in srgb,var(--mmb-panel) 94%,transparent);-webkit-backdrop-filter:blur(22px);backdrop-filter:blur(22px);
    border-right:1px solid var(--mmb-line);transform:translateX(-101%);transition:transform .26s cubic-bezier(.2,.8,.2,1)}
  #mmb-panel:not(.max).show-side .mmb-threads{transform:none;box-shadow:var(--mmb-shadow-side)}
  #mmb-panel:not(.max) .mmb-sidescrim{position:absolute;inset:0;z-index:5;background:var(--mmb-sidescrim);opacity:0;pointer-events:none;transition:opacity .2s ease}
  #mmb-panel:not(.max).show-side .mmb-sidescrim{opacity:1;pointer-events:auto}
  .mmb-scroll{flex:1;overflow-y:auto;overflow-anchor:none;padding:20px clamp(18px,6%,64px);display:flex;flex-direction:column;gap:15px}
  /* thin violet-tinted scrollbars (scroller + threads) */
  .mmb-scroll,.mmb-threads,.mmb-code pre,.mmb-table{scrollbar-width:thin;scrollbar-color:color-mix(in srgb,var(--mmb-violet) 40%,transparent) transparent}
  .mmb-scroll::-webkit-scrollbar,.mmb-threads::-webkit-scrollbar{width:8px;height:8px}
  .mmb-scroll::-webkit-scrollbar-thumb,.mmb-threads::-webkit-scrollbar-thumb{background:color-mix(in srgb,var(--mmb-violet) 34%,transparent);border-radius:8px;border:2px solid transparent;background-clip:padding-box}
  .mmb-scroll::-webkit-scrollbar-thumb:hover,.mmb-threads::-webkit-scrollbar-thumb:hover{background:color-mix(in srgb,var(--mmb-violet) 52%,transparent);background-clip:padding-box}
  .mmb-scroll::-webkit-scrollbar-track,.mmb-threads::-webkit-scrollbar-track{background:transparent}
  #mmb-panel.max .mmb-scroll{padding:26px clamp(24px,10%,120px)}
  .mmb-empty{flex:1;display:flex;flex-direction:column;justify-content:center}
  .mmb-hero h1{margin:0;font:800 clamp(22px,3vw,38px)/1.1 var(--mmb-font);letter-spacing:-.02em}
  #mmb-panel:not(.max) .mmb-hero h1{font-size:22px}
  .mmb-hero .g1{background:linear-gradient(90deg,color-mix(in srgb,var(--mmb-text) 66%,var(--mmb-muted)),var(--mmb-muted));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
  .mmb-hero .nm{background:linear-gradient(90deg,var(--mmb-violet),var(--mmb-glow));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
  .mmb-hero .g2{background:linear-gradient(90deg,var(--mmb-text) 30%,var(--mmb-violet));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
  .mmb-hero p{margin:11px 0 0;color:var(--mmb-muted);font:400 14px/1.5 var(--mmb-font);max-width:460px}
  #mmb-panel:not(.max) .mmb-hero p{font-size:13px}
  .mmb-cards{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-top:20px;max-width:620px}
  #mmb-panel.max .mmb-cards{grid-template-columns:repeat(4,1fr);max-width:920px}
  #mmb-panel:not(.max) .mmb-cards{grid-template-columns:1fr;gap:8px}
  .mmb-cardp{text-align:left;cursor:pointer;font-family:var(--mmb-font);color:var(--mmb-text);
    background:var(--mmb-card);border:1px solid var(--mmb-line);
    -webkit-backdrop-filter:blur(10px);backdrop-filter:blur(10px);border-radius:15px;padding:14px;min-height:104px;
    display:flex;flex-direction:column;justify-content:space-between;gap:10px;transition:transform .14s,border-color .14s,background .14s}
  /* Compact rows read left-to-right from the glyph, like every other row in the widget.
     The column layout's justify-content:space-between followed the flex-direction flip into
     the row and shoved the copy against the right edge — ragged-left text hanging off the
     far side of a 26px icon, which is how the openers shipped. */
  #mmb-panel:not(.max) .mmb-cardp{min-height:0;flex-direction:row;align-items:center;justify-content:flex-start;padding:12px 13px}
  #mmb-panel:not(.max) .mmb-cardp .cp{flex:1;min-width:0}
  .mmb-cardp:hover{transform:translateY(-2px);border-color:color-mix(in srgb,var(--mmb-info) 42%,transparent);
    background:color-mix(in srgb,var(--mmb-info) 9%,var(--mmb-card))}
  .mmb-cardp .cp{font:500 12.5px/1.35 var(--mmb-font);color:color-mix(in srgb,var(--mmb-text) 88%,var(--mmb-muted))}
  .mmb-cardp .ci{width:26px;height:26px;flex:none;border-radius:8px;display:grid;place-items:center;color:var(--mmb-info);background:color-mix(in srgb,var(--mmb-info) 12%,transparent)}
  .mmb-cardp .ci svg{width:15px;height:15px;stroke:currentColor;fill:none;stroke-width:1.8;transition:transform .22s var(--mmb-ease)}
  .mmb-cardp:hover .ci{background:color-mix(in srgb,var(--mmb-info) 20%,transparent)}
  .mmb-cardp:hover .ci svg{transform:scale(1.08)}
  .mmb-cardp:active{transform:translateY(0) scale(.995)}
  .mmb-cardp:focus-visible{outline:2px solid color-mix(in srgb,var(--mmb-info) 70%,transparent);outline-offset:2px}
  /* ── opening choreography ─────────────────────────────────────────────────────
     The panel morph, the greeting and the four openers are ONE gesture, not four
     effects: the greeting resolves first, the openers follow it in reading order, and
     the whole sequence is over inside 500ms so the box is never a thing you wait for.
     backwards, not both — a filled animation would keep owning the transform and eat the
     hover lift underneath it. */
  .mmb-hero h1{animation:mmb-rise .5s var(--mmb-ease) backwards}
  .mmb-hero p{animation:mmb-rise .5s .06s var(--mmb-ease) backwards}
  .mmb-cards .mmb-cardp{animation:mmb-rise .46s var(--mmb-ease) backwards;animation-delay:calc(var(--i,0)*55ms + 110ms)}
  @keyframes mmb-rise{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
  /* messages */
  .mmb-msg{display:flex;flex-direction:column;gap:4px;max-width:88%}
  .mmb-msg.user{align-self:flex-end;align-items:flex-end;max-width:78%;animation:mmb-pop .34s var(--mmb-ease) backwards}
  .mmb-msg.assistant{align-self:flex-start;align-items:flex-start;max-width:100%;width:100%}
  @keyframes mmb-pop{from{opacity:0;transform:translateY(14px) scale(.94)}60%{opacity:1}to{opacity:1;transform:none}}
  @media(prefers-reduced-motion:reduce){.mmb-msg.user{animation:none}}
  .mmb-bub{font:14.5px/1.62 var(--mmb-font);word-break:break-word}
  /* USER: keep the violet-tinted gradient bubble */
  .mmb-msg.user .mmb-bub{padding:12px 15px;border-radius:16px;background:linear-gradient(180deg,color-mix(in srgb,var(--mmb-info) 92%,#fff),var(--mmb-info));color:#fff;border-bottom-right-radius:5px;box-shadow:0 8px 22px -10px color-mix(in srgb,var(--mmb-info) 70%,transparent)}
  /* ASSISTANT: ghost block — NO per-message background/border/blur (the panel blurs once,
     so a per-bubble backdrop-filter is a needless repaint). Orb glyph anchors top-left. */
  .mmb-msg.assistant .mmb-bub{position:relative;width:100%;padding:2px 0 0 28px;background:none;border:none;box-shadow:none}
  .mmb-orbmark{position:absolute;left:0;top:1px;width:18px;height:18px;display:grid;place-items:center;pointer-events:none}
  .mmb-orbmark svg{width:18px;height:18px;fill:color-mix(in srgb,var(--mmb-violet) 85%,transparent)}
  .mmb-bub p{margin:0 0 9px}.mmb-bub p:last-child{margin-bottom:0}
  .mmb-bub ul,.mmb-bub ol{margin:7px 0 9px 20px;padding:0}.mmb-bub li{margin:4px 0}
  .mmb-bub strong{font-weight:700;color:color-mix(in srgb,var(--mmb-text) 92%,var(--mmb-hi))}
  .mmb-bub em{font-style:italic;color:color-mix(in srgb,var(--mmb-text) 88%,var(--mmb-muted))}
  .mmb-bub h4{margin:14px 0 6px;font:700 15.5px/1.3 var(--mmb-font);color:color-mix(in srgb,var(--mmb-text) 95%,var(--mmb-hi))}
  .mmb-bub h5{margin:12px 0 5px;font:700 14.5px/1.3 var(--mmb-font);color:color-mix(in srgb,var(--mmb-text) 92%,var(--mmb-hi))}
  .mmb-bub h4:first-child,.mmb-bub h5:first-child{margin-top:0}
  .mmb-bub code{font:13px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;background:color-mix(in srgb,var(--mmb-ink) 7%,transparent);border-radius:6px;padding:1.5px 6px}
  .mmb-bub a{color:var(--mmb-info);text-decoration:none}.mmb-bub a:hover{text-decoration:underline}
  .mmb-hr{border:none;border-top:1px solid color-mix(in srgb,var(--mmb-ink) 8%,transparent);margin:12px 0}
  .mmb-bq{margin:8px 0;padding:2px 0 2px 12px;border-left:2px solid var(--mmb-violet);color:var(--mmb-muted)}
  /* fenced code block */
  .mmb-code{margin:10px 0;border-radius:10px;border:1px solid color-mix(in srgb,var(--mmb-ink) 8%,transparent);background:color-mix(in srgb,var(--mmb-ink) 5%,transparent);overflow:hidden}
  .mmb-code-bar{display:flex;align-items:center;justify-content:space-between;padding:5px 10px;border-bottom:1px solid color-mix(in srgb,var(--mmb-ink) 7%,transparent)}
  .mmb-code-lang{font:600 10.5px/1 ui-monospace,monospace;letter-spacing:.04em;text-transform:uppercase;color:var(--mmb-muted)}
  .mmb-code-copy{border:none;background:transparent;color:var(--mmb-muted);font:600 11px/1 var(--mmb-font);cursor:pointer;padding:3px 6px;border-radius:6px;transition:color .12s,background .12s}
  .mmb-code-copy:hover{color:var(--mmb-text);background:color-mix(in srgb,var(--mmb-ink) 8%,transparent)}
  .mmb-code pre{margin:0;padding:12px;overflow-x:auto;-webkit-overflow-scrolling:touch}
  .mmb-code code{background:none;padding:0;border-radius:0;tab-size:2;-moz-tab-size:2;font:12.5px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace;color:color-mix(in srgb,var(--mmb-text) 94%,var(--mmb-hi));white-space:pre}
  /* pipe table */
  .mmb-table{border-collapse:collapse;margin:10px 0;font:13px/1.45 var(--mmb-font);width:100%;display:block;overflow-x:auto}
  .mmb-table th,.mmb-table td{border:1px solid color-mix(in srgb,var(--mmb-ink) 8%,transparent);padding:6px 10px;text-align:left;white-space:nowrap}
  .mmb-table th{font-weight:700;background:color-mix(in srgb,var(--mmb-ink) 4%,transparent);color:color-mix(in srgb,var(--mmb-text) 94%,var(--mmb-hi))}
  /* open-block streaming: plain text + per-frame fade-in ink spans */
  .mmb-open{white-space:pre-wrap;word-break:break-word}
  .mmb-ink{animation:mmb-inkin .16s ease both}
  @keyframes mmb-inkin{from{opacity:0}to{opacity:1}}
  @media(prefers-reduced-motion:reduce){.mmb-ink{animation:none}}
  /* streaming caret */
  .mmb-caret{display:inline-block;width:2px;height:15px;vertical-align:-2px;margin-left:1px;border-radius:2px;background:var(--mmb-violet);animation:mmb-caret 1s ease-in-out infinite}
  @keyframes mmb-caret{0%,100%{opacity:1}50%{opacity:.25}}
  @media(prefers-reduced-motion:reduce){.mmb-caret{animation:none}}
  .mmb-stopped{color:var(--mmb-muted);font-style:italic;font-size:13px}
  /* fallback container: the server's own SVG, used only when the live engine below has
     no bars for the symbol. No watermark chrome is added here — that belongs to the
     social-post renderer, not to a reply. */
  .mmb-bub .mmb-chart{margin:10px 0 2px;border-radius:12px;overflow:hidden;border:1px solid color-mix(in srgb,var(--mmb-ink) 8%,transparent);background:#0E1420}
  .mmb-bub .mmb-chart svg{display:block;width:100%;height:auto}
  /* ── the in-chat chart ───────────────────────────────────────────────────────
     Drawn here, live, from the desk's own daily bars — not a picture of a chart.
     What that buys: a real price axis, panes that are not squeezed, indicators
     computed over the FULL history (so no cold-start stub at the left edge), a
     crosshair that reads the bar under the cursor, and a build sequence you can
     watch. The gradient is the widget's own; the social renderer's watermark,
     logo and CTA have no business inside a reply. */
  #mmb-root{--mmb-up:#45b873;--mmb-dn:#e06464;--mmb-cx-a:#101725;--mmb-cx-b:#0a0d14;--mmb-cx-grid:#fff}
  html[data-theme="light"] #mmb-root{--mmb-up:#1f9a55;--mmb-dn:#cf4040;--mmb-cx-a:#ffffff;--mmb-cx-b:#eaeff7;--mmb-cx-grid:#1c2430}
  /* 红涨绿跌 — a price chart IS a market-direction read, so it takes the Asia
     convention in Chinese exactly like the site's boards do (theme.css swaps
     --up/--down under html[data-lang=zh]; the widget owns its own tokens because it
     also runs on the Terminal, where theme.css is not loaded). */
  html[data-lang="zh"] #mmb-root{--mmb-up:#e06464;--mmb-dn:#45b873}
  html[data-theme="light"][data-lang="zh"] #mmb-root{--mmb-up:#cf4040;--mmb-dn:#1f9a55}
  .mmb-cx{position:relative;margin:12px 0 4px;border-radius:14px;overflow:hidden;
    border:1px solid color-mix(in srgb,var(--mmb-ink) 11%,transparent);
    background:radial-gradient(120% 88% at 6% -12%,color-mix(in srgb,var(--mmb-info) 15%,transparent),transparent 58%),
      radial-gradient(86% 70% at 104% -6%,color-mix(in srgb,var(--mmb-violet) 13%,transparent),transparent 56%),
      linear-gradient(180deg,var(--mmb-cx-a),var(--mmb-cx-b));
    box-shadow:var(--mmb-shadow-box);animation:mmb-cx-in .5s var(--mmb-ease) backwards}
  @keyframes mmb-cx-in{from{opacity:0;transform:translateY(10px) scale(.985)}to{opacity:1;transform:none}}
  .mmb-cx-h{display:flex;align-items:baseline;gap:9px;padding:11px 14px 6px;min-height:34px}
  .mmb-cx-sym{flex:none;white-space:nowrap;font:800 15px/1 var(--mmb-font);letter-spacing:-.01em;color:color-mix(in srgb,var(--mmb-text) 97%,var(--mmb-hi))}
  .mmb-cx-tf{flex:none;white-space:nowrap;font:700 9.5px/1 var(--mmb-font);letter-spacing:.09em;text-transform:uppercase;color:var(--mmb-muted);
    border:1px solid color-mix(in srgb,var(--mmb-ink) 15%,transparent);border-radius:5px;padding:3px 5px}
  .mmb-cx-h .sp{flex:1;min-width:4px}
  /* the readout: last price at rest, the hovered bar while the crosshair is live. It is the
     part that GIVES WAY when the card is narrow — volume drops first, then it ellipsises.
     The symbol never wraps: an "AAP / L" header is the card losing its own name. */
  .mmb-cx-read{display:flex;align-items:baseline;justify-content:flex-end;gap:7px;min-width:0;
    font:600 11px/1.2 var(--mmb-mono);color:var(--mmb-muted);
    font-variant-numeric:tabular-nums;white-space:nowrap;overflow:hidden}
  .mmb-cx.narrow .mmb-cx-vol{display:none}
  .mmb-cx-last{font:800 15px/1 var(--mmb-mono);color:color-mix(in srgb,var(--mmb-text) 97%,var(--mmb-hi));font-variant-numeric:tabular-nums}
  .mmb-cx-chg{font:700 11.5px/1 var(--mmb-mono);font-variant-numeric:tabular-nums}
  .mmb-cx-chg.up{color:var(--mmb-up)}.mmb-cx-chg.dn{color:var(--mmb-dn)}
  .mmb-cx-read b{font-weight:700;color:color-mix(in srgb,var(--mmb-text) 88%,var(--mmb-muted))}
  .mmb-cx svg{display:block;width:100%;height:auto;touch-action:pan-y}
  .mmb-cx-foot{display:flex;align-items:center;gap:10px;padding:0 14px 10px;font:10.5px/1.3 var(--mmb-font);color:var(--mmb-muted)}
  .mmb-cx-key{display:inline-flex;align-items:center;gap:4px}
  .mmb-cx-key i{width:11px;height:2px;border-radius:2px;display:inline-block;background:currentColor}
  .mmb-cx-foot .sp{flex:1}
  .mmb-cx-src{opacity:.75;font:10px/1.3 var(--mmb-mono)}
  /* build sequence — candles rise from their own base, lines draw themselves, panes
     resolve after the price. One gesture, ~1.3s end to end, then it is a static chart. */
  .mmb-cx .cndl,.mmb-cx .vbar,.mmb-cx .hbar{transform-box:fill-box;transform-origin:center bottom;
    animation:mmb-cx-grow .34s var(--mmb-ease) backwards}
  .mmb-cx .hbar{transform-origin:center center}
  @keyframes mmb-cx-grow{from{transform:scaleY(.02);opacity:.2}to{transform:none;opacity:1}}
  .mmb-cx .draw{animation:mmb-cx-draw 1.1s var(--mmb-ease) backwards}
  @keyframes mmb-cx-draw{from{stroke-dashoffset:var(--len)}to{stroke-dashoffset:0}}
  .mmb-cx .fade{animation:mmb-cx-fade .5s var(--mmb-ease) backwards}
  @keyframes mmb-cx-fade{from{opacity:0}to{opacity:1}}
  .mmb-cx .pop{transform-box:fill-box;transform-origin:left center;animation:mmb-cx-pop .42s var(--mmb-ease) backwards}
  @keyframes mmb-cx-pop{from{opacity:0;transform:translateX(-6px) scale(.9)}to{opacity:1;transform:none}}
  .mmb-cx-xh{opacity:0;transition:opacity .12s ease}
  .mmb-cx.live .mmb-cx-xh{opacity:1}
  /* a chart that could not be drawn says so in a line rather than leaving a hole */
  .mmb-cx-miss{padding:14px;font:12.5px/1.5 var(--mmb-font);color:var(--mmb-muted)}
  @media(prefers-reduced-motion:reduce){
    .mmb-cx,.mmb-cx .cndl,.mmb-cx .vbar,.mmb-cx .hbar,.mmb-cx .draw,.mmb-cx .fade,.mmb-cx .pop{animation:none}
    .mmb-cx .draw{stroke-dashoffset:0}}
  .mmb-txt:empty,.mmb-charts:empty{display:none}
  /* assistant action row (copy · regenerate · timestamp) — space always reserved */
  .mmb-actions{display:flex;align-items:center;gap:6px;height:22px;margin-top:5px;opacity:0;transition:opacity .14s ease}
  .mmb-msg.assistant:hover .mmb-actions,.mmb-msg.assistant:focus-within .mmb-actions{opacity:1}
  @media(hover:none),(pointer:coarse){.mmb-actions{opacity:.75}}
  .mmb-abtn{width:22px;height:22px;border:none;background:transparent;border-radius:7px;color:var(--mmb-muted);cursor:pointer;display:grid;place-items:center;padding:0;transition:color .12s,background .12s}
  .mmb-abtn:hover{color:var(--mmb-text);background:color-mix(in srgb,var(--mmb-ink) 7%,transparent)}
  .mmb-abtn svg{width:15px;height:15px;stroke:currentColor;fill:none;stroke-width:1.8}
  .mmb-abtn.mmb-copy svg{width:14px;height:14px}
  .mmb-regen{display:none}
  .mmb-msg.assistant.mmb-last .mmb-regen{display:grid}
  .mmb-time{font:11px/1 var(--mmb-font);color:var(--mmb-muted);margin-left:2px}
  /* day separator between history messages */
  .mmb-daysep{display:flex;align-items:center;justify-content:center;margin:6px 0 2px}
  .mmb-daysep span{font:600 10.5px/1 var(--mmb-font);letter-spacing:.05em;color:var(--mmb-muted);background:color-mix(in srgb,var(--mmb-ink) 4%,transparent);border-radius:999px;padding:4px 12px}
  /* inline error / retry card */
  .mmb-errcard{display:flex;flex-direction:column;align-items:flex-start;gap:9px;padding:12px 14px;border-radius:12px;background:color-mix(in srgb,var(--mmb-danger) 8%,color-mix(in srgb,var(--mmb-panel) 55%,transparent));border:1px solid color-mix(in srgb,var(--mmb-danger) 26%,transparent)}
  .mmb-errline{font:400 13.5px/1.5 var(--mmb-font);color:color-mix(in srgb,var(--mmb-text) 90%,var(--mmb-muted))}
  .mmb-retry{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--mmb-line);background:color-mix(in srgb,var(--mmb-ink) 5%,transparent);color:var(--mmb-text);font:600 12.5px/1 var(--mmb-font);border-radius:9px;padding:7px 13px;cursor:pointer;transition:border-color .13s,background .13s}
  .mmb-retry:hover{border-color:color-mix(in srgb,var(--mmb-info) 42%,transparent);background:color-mix(in srgb,var(--mmb-info) 8%,transparent)}
  .mmb-retry svg{width:14px;height:14px;stroke:currentColor;fill:none;stroke-width:1.8}
  /* visually-hidden live region */
  .mmb-sr{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}
  @media print{#mmb-root{display:none!important}}
  @keyframes mmb-pulse{0%,100%{opacity:.4;transform:scale(.85)}50%{opacity:1;transform:scale(1.1)}}
  /* ── the reasoning ledger ────────────────────────────────────────────────────
     The gateway holds the answer back until it clears the advice filter, so the wait
     is the only thing the user has — and a spinner spends it saying nothing. This is
     the widget's signature surface: a worksheet that assembles itself downward.

       history above  ·  the live line at the bottom  ·  the answer directly beneath

     Log order, not stack order: the finished steps sit ABOVE the line that is running,
     so the eye travels down through the work and straight into the reply that follows
     it. A spine threads the nodes — each finished step leaves a filled node on it, so
     "how much did it actually do" is legible without reading a single word.

     Every visible string still arrives from the wire (server-owned bilingual labels,
     leak law); what this file adds is STRUCTURE — a family glyph per step, the ticker
     as a data chip, and one plain-language clause under the live label saying what
     this phase is for. */
  .mmb-think{position:relative;display:flex;flex-direction:column;gap:2px;padding:1px 0 2px}
  .mmb-tk-rows{position:relative;display:flex;flex-direction:column;gap:2px}
  /* The spine threads the travelled nodes and stops AT the live one — it is the path
     already walked, so it must not dangle past the line still running (an open tail below
     the last node reads as a rendering artefact, not as "more to come"). It brightens on
     the way down because that end is now. Drawn on the rows, so a turn that has not
     retired a step yet shows no stub at all. */
  .mmb-tk-rows::before{content:'';position:absolute;left:8px;top:11px;bottom:-14px;width:1px;pointer-events:none;
    background:linear-gradient(180deg,color-mix(in srgb,var(--mmb-info) 16%,transparent),
      color-mix(in srgb,var(--mmb-info) 34%,transparent))}
  .mmb-tk-rows:empty::before{display:none}
  .mmb-tk-row,.mmb-tk-h{display:grid;grid-template-columns:17px minmax(0,1fr) auto;align-items:start;gap:8px;padding:2px 0}
  /* the live line's qualifier rides WITH its label (one flex row) rather than in the grid's
     third track — that track belongs to the clock, and a display:none chip in a track of
     its own would leave the gutter behind it. */
  .mmb-tk-h .lbrow{display:flex;align-items:center;gap:6px;min-width:0}
  .mmb-tk-row{animation:mmb-row-in .34s var(--mmb-ease) backwards}
  @keyframes mmb-row-in{from{opacity:0;transform:translateY(-4px)}to{opacity:1;transform:none}}
  /* a node on the spine: filled tile = a step that finished */
  .mmb-tk-ic{width:17px;height:17px;flex:none;border-radius:6px;display:grid;place-items:center;position:relative;
    background:color-mix(in srgb,var(--mmb-info) 13%,var(--mmb-panel));color:color-mix(in srgb,var(--mmb-info) 78%,var(--mmb-muted))}
  .mmb-tk-ic svg{width:11px;height:11px;stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
  .mmb-tk-row .mmb-tk-ic{opacity:var(--mmb-step-o)}
  .mmb-tk-row .rl{font:11.5px/1.45 var(--mmb-font);color:var(--mmb-muted);opacity:var(--mmb-step-o);min-width:0;
    overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  /* the ticker is a figure, not a word — mono, so AAPL/600036.SS line up down the rail */
  .rd{flex:none;font:600 10px/1.5 var(--mmb-mono);letter-spacing:.02em;color:color-mix(in srgb,var(--mmb-info) 82%,var(--mmb-text));
    background:color-mix(in srgb,var(--mmb-info) 11%,transparent);border-radius:5px;padding:1px 5px;margin-top:1px}
  .rn{flex:none;font:600 10px/1.5 var(--mmb-mono);color:var(--mmb-muted);margin-top:1px}
  /* the live line: the one lit thing on the strip */
  .mmb-tk-h .mmb-tk-ic{background:color-mix(in srgb,var(--mmb-info) 20%,var(--mmb-panel));color:var(--mmb-info)}
  /* one travelling arc on the live node — the same instrument the launcher wears, so the
     "working" signal is one idiom across the widget rather than a second invented one. */
  @supports ((-webkit-mask-composite:xor) or (mask-composite:exclude)){
    .mmb-tk-h .mmb-tk-ic::after{content:'';position:absolute;inset:-1.5px;border-radius:7px;padding:1.5px;pointer-events:none;
      background:conic-gradient(from var(--mmb-ang),transparent 0 52%,var(--mmb-violet) 74%,var(--mmb-info) 88%,transparent 96%);
      -webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);-webkit-mask-composite:xor;
      mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);mask-composite:exclude;
      animation:mmb-rim 1.9s linear infinite}
  }
  .mmb-tk-body{min-width:0;display:flex;flex-direction:column;gap:1px}
  .mmb-tk-h .lb{font:600 12.5px/1.4 var(--mmb-font);color:color-mix(in srgb,var(--mmb-text) 86%,var(--mmb-muted));
    min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  /* the label crossfades on a phase change instead of snapping — the strip updates ~6
     times a turn and a hard text swap reads as a flicker at that cadence. */
  .mmb-tk-h .lb.mmb-swap{animation:mmb-lab-in .26s var(--mmb-ease) backwards}
  @keyframes mmb-lab-in{from{opacity:0;transform:translateY(3px)}to{opacity:1;transform:none}}
  .mmb-tk-h .sb{font:11px/1.4 var(--mmb-font);color:var(--mmb-muted);opacity:.88;min-width:0;
    overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .mmb-tk-t{flex:none;font:11px/1.6 var(--mmb-mono);color:var(--mmb-muted);font-variant-numeric:tabular-nums}
  /* Deep Research declares itself as the ledger's first line and then STAYS there while
     the steps rotate under it: this turn is meant to take longer, and a standing header
     is cheaper than a user wondering why the wait is different. */
  .mmb-tk-row.mode .mmb-tk-ic{background:color-mix(in srgb,var(--mmb-violet) 16%,var(--mmb-panel));
    color:color-mix(in srgb,var(--mmb-violet) 92%,var(--mmb-hi));opacity:1}
  .mmb-tk-row.mode .rl{color:color-mix(in srgb,var(--mmb-text) 74%,var(--mmb-muted));opacity:1;font-weight:600}
  /* after the answer lands: one muted receipt line; click unfolds what was checked */
  .mmb-recap{margin:0 0 9px}
  .mmb-chip{display:inline-flex;align-items:center;gap:6px;padding:0;border:none;background:none;cursor:pointer;
    font:11.5px/1.4 var(--mmb-font);color:var(--mmb-muted);text-align:left;transition:color .13s}
  .mmb-chip:hover{color:color-mix(in srgb,var(--mmb-text) 72%,var(--mmb-muted))}
  .mmb-chip .ck{width:12px;height:12px;flex:none;stroke:currentColor;fill:none;stroke-width:1.9;stroke-linecap:round;stroke-linejoin:round;opacity:.8}
  .mmb-chip::after{content:'';width:5px;height:5px;flex:none;border-right:1.2px solid currentColor;border-bottom:1.2px solid currentColor;
    transform:translateY(-1px) rotate(45deg);transition:transform .2s var(--mmb-ease)}
  .mmb-recap.on .mmb-chip::after{transform:translateY(1px) rotate(-135deg)}
  .mmb-recap-list{display:none;flex-direction:column;gap:2px;margin:7px 0 0;padding:0 0 0 1px;position:relative}
  .mmb-recap.on .mmb-recap-list{display:flex;animation:mmb-recap-in .3s var(--mmb-ease) backwards}
  @keyframes mmb-recap-in{from{opacity:0;transform:translateY(-3px)}to{opacity:1;transform:none}}
  .mmb-recap-list::before{content:'';position:absolute;left:8px;top:9px;bottom:9px;width:1px;
    background:color-mix(in srgb,var(--mmb-ink) 10%,transparent);pointer-events:none}
  .mmb-recap-list .mmb-tk-row{animation:none}
  .mmb-recap-list .mmb-tk-ic{background:color-mix(in srgb,var(--mmb-ink) 7%,transparent);color:var(--mmb-muted)}
  .mmb-cites{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
  .mmb-cite{font:11px/1.3 var(--mmb-font);background:color-mix(in srgb,var(--mmb-info) 11%,transparent);border:1px solid color-mix(in srgb,var(--mmb-info) 26%,transparent);border-radius:999px;padding:3px 10px;color:color-mix(in srgb,var(--mmb-info) 86%,var(--mmb-text));text-decoration:none;cursor:pointer}
  .mmb-cite:hover{background:color-mix(in srgb,var(--mmb-info) 20%,transparent)}
  .mmb-meta{font:11px/1.4 var(--mmb-font);color:var(--mmb-muted);padding:0 4px}
  .mmb-upgrade{display:none;margin:0 0 12px;padding:13px 15px;border-radius:13px;font:13px/1.5 var(--mmb-font);
    background:color-mix(in srgb,var(--mmb-warn) 12%,color-mix(in srgb,var(--mmb-panel) 55%,transparent));border:1px solid color-mix(in srgb,var(--mmb-warn) 34%,transparent)}
  .mmb-upgrade a{color:var(--mmb-info);font-weight:700;text-decoration:underline}
  /* composer */
  .mmb-comp{position:relative;flex:none;padding:14px clamp(18px,6%,64px) 14px}
  #mmb-panel.max .mmb-comp{padding:14px clamp(24px,10%,120px) 16px}
  /* overflow is VISIBLE, deliberately. Nothing inside the box bleeds to its edge — the
     slash palette is inset by its own padding, the textarea and tool row are transparent —
     but the depth control's tip has to escape upward, and the old clip swallowed its first
     two lines. The palette's top corners are pinned below so losing the clip cannot square
     them off. */
  .mmb-box{border-radius:18px;border:1px solid var(--mmb-line);background:var(--mmb-boxbg);overflow:visible;
    -webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px);box-shadow:var(--mmb-shadow-box);
    transition:border-color .2s var(--mmb-ease-tint),box-shadow .2s var(--mmb-ease-tint)}
  .mmb-slash{border-radius:17px 17px 0 0}
  /* Focus lands on the textarea, but the RING belongs to the whole box — the box is what
     reads as the input. focus-within rather than :focus so clicking the lane control or
     the attach button never drops the frame the user is typing inside. */
  .mmb-box:focus-within{border-color:color-mix(in srgb,var(--mmb-info) 40%,transparent);
    box-shadow:var(--mmb-shadow-box),0 0 0 3px color-mix(in srgb,var(--mmb-info) 13%,transparent)}
  .mmb-ta:focus-visible{outline:none}   /* the box carries the ring; a second one inside it is noise */
  /* Send is the one moment the composer should answer back. A 240ms settle — the box dips
     and returns while the bubble it just launched rises into the transcript — so pressing
     the key FEELS like the message left, rather than like the text vanished. */
  .mmb-box.mmb-sent{animation:mmb-recoil .24s var(--mmb-ease)}
  @keyframes mmb-recoil{0%{transform:none}38%{transform:scale(.985) translateY(2px)}100%{transform:none}}
  @media(prefers-reduced-motion:reduce){.mmb-box.mmb-sent{animation:none}}
  .mmb-ctx{display:none;align-items:center;gap:7px;padding:9px 12px 0}
  .mmb-ctx.on{display:flex}
  .mmb-ctx .chip{display:inline-flex;align-items:center;gap:6px;white-space:nowrap;font:600 11.5px/1 var(--mmb-font);
    color:color-mix(in srgb,var(--mmb-info) 92%,var(--mmb-hi));background:color-mix(in srgb,var(--mmb-info) 13%,transparent);
    border:1px solid color-mix(in srgb,var(--mmb-info) 30%,transparent);border-radius:999px;padding:4px 11px 4px 8px}
  .mmb-ctx .chip .cx{width:13px;height:13px;flex:none;stroke:currentColor;fill:none;stroke-width:1.6;opacity:.9;animation:mmb-breathe 4.6s ease-in-out infinite}
  .mmb-ctx .chip b{font:700 11.5px/1 var(--mmb-font);letter-spacing:.03em;color:var(--mmb-text)}
  .mmb-thumbs{display:none;flex-wrap:wrap;gap:8px;padding:10px 12px 0}
  .mmb-thumbs.on{display:flex}
  .mmb-thumb{position:relative;width:52px;height:52px;border-radius:10px;overflow:hidden;border:1px solid var(--mmb-line);background:var(--mmb-plate);flex:none;
    animation:mmb-thumb-in .42s var(--mmb-ease) backwards;animation-delay:calc(var(--i,0)*55ms)}
  /* an attachment ARRIVES — it does not blink into existence. The rotation is tiny and
     unwinds: a picture being set down on the desk, not a card dealt at you. */
  @keyframes mmb-thumb-in{from{opacity:0;transform:translateY(10px) scale(.82) rotate(-4deg)}to{opacity:1;transform:none}}
  .mmb-thumb img{width:100%;height:100%;object-fit:cover;display:block}
  .mmb-thumb .x{position:absolute;top:2px;right:2px;width:16px;height:16px;border:none;border-radius:50%;cursor:pointer;display:grid;place-items:center;
    background:rgba(8,10,16,.82);color:#fff;font:700 11px/1 var(--mmb-font);padding:0;
    opacity:0;transform:scale(.7);transition:opacity .15s var(--mmb-ease),transform .15s var(--mmb-ease),background .13s}
  .mmb-thumb:hover .x,.mmb-thumb:focus-within .x{opacity:1;transform:none}
  @media(hover:none),(pointer:coarse){.mmb-thumb .x{opacity:1;transform:none}}
  .mmb-thumb .x:hover{background:var(--mmb-danger)}
  /* ── drag & drop ──────────────────────────────────────────────────────────────
     A chat that takes images should SAY so the moment a file crosses it. The overlay
     is the whole panel — a small target you have to aim at is the thing people miss —
     and it lights the frame it is asking you to drop into. */
  .mmb-drop{position:absolute;inset:0;z-index:20;display:grid;place-items:center;pointer-events:none;
    opacity:0;visibility:hidden;transition:opacity .2s var(--mmb-ease),visibility 0s linear .2s;
    background:color-mix(in srgb,var(--mmb-panel) 72%,transparent);
    -webkit-backdrop-filter:blur(10px) saturate(1.1);backdrop-filter:blur(10px) saturate(1.1)}
  #mmb-panel.dropping .mmb-drop{opacity:1;visibility:visible;transition-delay:0s,0s}
  .mmb-drop-in{display:flex;flex-direction:column;align-items:center;gap:12px;padding:26px 34px;text-align:center;
    border-radius:20px;border:2px dashed color-mix(in srgb,var(--mmb-info) 46%,transparent);
    background:color-mix(in srgb,var(--mmb-info) 7%,transparent);
    transform:scale(.94);transition:transform .26s var(--mmb-ease)}
  #mmb-panel.dropping .mmb-drop-in{transform:none}
  .mmb-drop-ic{position:relative;width:52px;height:52px;border-radius:16px;display:grid;place-items:center;
    color:#fff;background:linear-gradient(160deg,var(--mmb-violet),var(--mmb-glow));
    box-shadow:0 14px 34px -12px color-mix(in srgb,var(--mmb-glow) 80%,transparent)}
  .mmb-drop-ic svg{width:24px;height:24px;stroke:currentColor;fill:none;stroke-width:1.9;stroke-linecap:round;stroke-linejoin:round}
  #mmb-panel.dropping .mmb-drop-ic{animation:mmb-drop-hover 1.8s ease-in-out infinite}
  @keyframes mmb-drop-hover{0%,100%{transform:translateY(0)}50%{transform:translateY(-7px)}}
  /* the ring the icon is hovering over — it breathes on the offbeat, so the pair reads as
     one object in motion rather than two things pulsing together */
  .mmb-drop-ic::after{content:'';position:absolute;inset:-10px;border-radius:22px;
    border:1px solid color-mix(in srgb,var(--mmb-info) 40%,transparent)}
  #mmb-panel.dropping .mmb-drop-ic::after{animation:mmb-drop-ring 1.8s ease-in-out infinite}
  @keyframes mmb-drop-ring{0%,100%{transform:scale(1);opacity:.7}50%{transform:scale(1.12);opacity:.25}}
  .mmb-drop-t{font:700 15px/1.3 var(--mmb-font);color:color-mix(in srgb,var(--mmb-text) 96%,var(--mmb-hi))}
  .mmb-drop-s{font:400 12px/1.4 var(--mmb-font);color:var(--mmb-muted);max-width:220px}
  @media(prefers-reduced-motion:reduce){
    .mmb-thumb{animation:none}
    #mmb-panel.dropping .mmb-drop-ic,#mmb-panel.dropping .mmb-drop-ic::after{animation:none}
    .mmb-drop,.mmb-drop-in,.mmb-thumb .x{transition:none}}
  /* attached-image thumbs inside a sent user bubble */
  .mmb-bub .mmb-imgs{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px}
  .mmb-bub .mmb-imgs img{width:120px;max-width:44vw;height:auto;border-radius:10px;border:1px solid color-mix(in srgb,#fff 18%,transparent);display:block}
  .mmb-ta{width:100%;border:none;background:none;outline:none;resize:none;color:var(--mmb-text);font:15px/1.5 var(--mmb-font);padding:12px 14px 6px;min-height:26px;max-height:150px}
  .mmb-ta::placeholder{color:color-mix(in srgb,var(--mmb-muted) 92%,transparent)}
  .mmb-tools{display:flex;align-items:center;gap:8px;padding:6px 10px 10px}
  .mmb-tools .sp{flex:1}
  /* send-shortcut hint: earns its space only once there is something to send, which is
     also the moment the user is about to press Enter and expect it to go. */
  .mmb-hint{display:none;font:11px/1 var(--mmb-font);color:var(--mmb-muted);white-space:nowrap;opacity:.85;min-width:0;overflow:hidden;text-overflow:ellipsis}
  .mmb-box.mmb-typing .mmb-hint{display:inline}
  /* ── depth control (Fast / Pro / Deep) ────────────────────────────────────────
     The three stops are not "cheap / dear / dearer", they are how deep the desk digs for
     one question — so the marks are a depth family, drawn in this file rather than borrowed
     from the emoji table: Fast is a single strike, Pro a cut stone with several faces, Deep
     descends through the surface line. Fast and Pro take solid fills instead of the outline
     language the rest of the chrome uses — at 12px a 1.8-stroke mark silts up, and these are
     identity badges rather than affordances. */
  .mmb-seg{display:flex;flex:none;gap:2px;padding:2px;border-radius:999px;background:color-mix(in srgb,var(--mmb-ink) 5%,transparent);border:1px solid var(--mmb-line)}
  .mmb-seg button{display:inline-flex;align-items:center;gap:5px;border:none;background:transparent;color:var(--mmb-muted);
    font:600 11.5px/1 var(--mmb-font);padding:5px 11px 5px 9px;border-radius:999px;cursor:pointer;white-space:nowrap;
    transition:color .16s var(--mmb-ease-tint),background .16s var(--mmb-ease-tint),box-shadow .16s var(--mmb-ease-tint)}
  .mmb-seg button svg{width:12px;height:12px;flex:none;fill:currentColor;stroke:none}
  .mmb-seg button:hover{color:color-mix(in srgb,var(--mmb-text) 80%,var(--mmb-muted))}
  .mmb-seg button.on:hover{color:#fff}
  .mmb-seg button.on{background:linear-gradient(180deg,color-mix(in srgb,var(--mmb-info) 92%,#fff),var(--mmb-info));color:#fff;box-shadow:0 2px 10px -3px color-mix(in srgb,var(--mmb-info) 70%,transparent)}
  /* the facet lines inside the Pro stone: same ink, dialled back, so the mark reads as
     cut rather than as a filled diamond. One global rule — the stone also wears the
     meter and would otherwise arrive un-cut there. */
  #mmb-root .fc{fill:none;stroke:currentColor;stroke-width:1.25;opacity:.4}
  .mmb-seg button:focus-visible{outline:2px solid color-mix(in srgb,var(--mmb-info) 70%,transparent);outline-offset:2px}
  /* the meter wears the lane's own mark, so "which lane am I spending" needs no reading */
  .mmb-q{display:inline-flex;align-items:center;gap:4px;font:600 11px/1 var(--mmb-mono);color:var(--mmb-muted);padding:0 2px;white-space:nowrap;font-variant-numeric:tabular-nums}
  .mmb-q svg{width:11px;height:11px;flex:none;fill:currentColor;stroke:none;opacity:.9}
  .mmb-q:empty{display:none}
  .mmb-q.warn{color:var(--mmb-warn)}.mmb-q.empty{color:var(--mmb-danger)}
  .mmb-tbtn{width:34px;height:34px;border:none;background:transparent;border-radius:10px;color:var(--mmb-muted);cursor:pointer;display:grid;place-items:center;
    transition:background .14s var(--mmb-ease-tint),color .14s var(--mmb-ease-tint),transform .14s var(--mmb-ease)}
  .mmb-tbtn:hover{background:color-mix(in srgb,var(--mmb-ink) 7%,transparent);color:var(--mmb-text)}
  .mmb-tbtn:active{transform:scale(.92)}
  .mmb-tbtn:focus-visible{outline:2px solid color-mix(in srgb,var(--mmb-info) 70%,transparent);outline-offset:2px}
  .mmb-tbtn svg{width:18px;height:18px;stroke:currentColor;fill:none;stroke-width:1.8}
  .mmb-send{position:relative;width:36px;height:36px;border:none;border-radius:12px;cursor:pointer;display:grid;place-items:center;color:#fff;
    background:linear-gradient(180deg,color-mix(in srgb,var(--mmb-info) 92%,#fff),var(--mmb-info));box-shadow:0 6px 18px -6px color-mix(in srgb,var(--mmb-info) 75%,transparent);
    transition:transform .16s var(--mmb-ease),box-shadow .16s var(--mmb-ease),opacity .16s ease,background .16s ease}
  .mmb-send:not(:disabled):hover{transform:translateY(-1px);box-shadow:0 9px 22px -7px color-mix(in srgb,var(--mmb-info) 80%,transparent)}
  .mmb-send:not(:disabled):active{transform:translateY(0) scale(.93)}
  .mmb-send:disabled{opacity:.4;cursor:not-allowed;box-shadow:none;transform:none}
  .mmb-send:focus-visible{outline:2px solid color-mix(in srgb,var(--mmb-info) 70%,transparent);outline-offset:2px}
  .mmb-send svg{width:17px;height:17px;stroke:currentColor;fill:none;stroke-width:2;transition:opacity .14s ease}
  /* streaming: arrow crossfades to a rounded stop square (opacity-only morph) */
  .mmb-send::after{content:'';position:absolute;width:12px;height:12px;border-radius:3px;background:#fff;opacity:0;transition:opacity .14s ease;pointer-events:none}
  .mmb-send.mmb-stop{background:linear-gradient(180deg,color-mix(in srgb,var(--mmb-violet) 92%,#fff),var(--mmb-violet));box-shadow:0 6px 18px -6px color-mix(in srgb,var(--mmb-violet) 75%,transparent);opacity:1}
  .mmb-send.mmb-stop svg{opacity:0}
  .mmb-send.mmb-stop::after{opacity:1}
  /* jump-to-latest pill (violet glass, above composer) */
  .mmb-jump{position:absolute;left:50%;bottom:calc(100% + 12px);transform:translate(-50%,6px);z-index:8;display:inline-flex;align-items:center;gap:5px;
    border:1px solid color-mix(in srgb,var(--mmb-violet) 34%,transparent);border-radius:999px;padding:6px 13px 6px 10px;cursor:pointer;
    color:color-mix(in srgb,var(--mmb-violet) 88%,var(--mmb-hi));background:color-mix(in srgb,var(--mmb-violet) 14%,color-mix(in srgb,var(--mmb-panel) 82%,transparent));
    -webkit-backdrop-filter:blur(12px);backdrop-filter:blur(12px);font:600 12px/1 var(--mmb-font);opacity:0;pointer-events:none;
    box-shadow:var(--mmb-shadow-pop);transition:opacity .2s ease,transform .2s ease}
  .mmb-jump.on{opacity:1;pointer-events:auto;transform:translate(-50%,0)}
  .mmb-jump svg{width:14px;height:14px;stroke:currentColor;fill:none;stroke-width:2}
  .mmb-main{position:relative}
  @media(prefers-reduced-motion:reduce){.mmb-jump{transition:opacity .2s ease}}
  /* char counter reuses the .mmb-q slot */
  .mmb-q.mmb-count{color:var(--mmb-muted)}.mmb-q.mmb-count.warn{color:var(--mmb-danger)}
  /* slash palette (above composer, inside the box) */
  .mmb-slash{display:flex;flex-direction:column;padding:6px;gap:2px;border-bottom:1px solid color-mix(in srgb,var(--mmb-ink) 7%,transparent)}
  .mmb-slash-i{display:grid;grid-template-columns:24px auto 1fr;align-items:center;gap:9px;border:none;background:transparent;border-radius:9px;padding:8px 10px;cursor:pointer;text-align:left;font-family:var(--mmb-font);color:var(--mmb-text)}
  .mmb-slash-i.on{background:color-mix(in srgb,var(--mmb-info) 12%,transparent)}
  .mmb-slash-i .si{width:24px;height:24px;border-radius:7px;display:grid;place-items:center;color:var(--mmb-info);background:color-mix(in srgb,var(--mmb-info) 12%,transparent)}
  .mmb-slash-i .si svg{width:14px;height:14px;stroke:currentColor;fill:none;stroke-width:1.8}
  .mmb-slash-i .sn{font:700 12.5px/1 var(--mmb-font);color:var(--mmb-text)}
  .mmb-slash-i .sh{font:400 11.5px/1 var(--mmb-font);color:var(--mmb-muted);text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  /* focus-visible rings on new controls (house style) */
  .mmb-abtn:focus-visible,.mmb-retry:focus-visible,.mmb-jump:focus-visible,.mmb-slash-i:focus-visible,.mmb-code-copy:focus-visible,.mmb-ti-act:focus-visible,.mmb-chip:focus-visible{outline:2px solid color-mix(in srgb,var(--mmb-info) 70%,transparent);outline-offset:2px}
  /* signed-out */
  .mmb-gate{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:30px 22px;gap:14px}
  .mmb-gate .mmb-orb{width:64px;height:64px}.mmb-gate .mmb-orb svg{width:30px;height:30px}
  .mmb-gate h2{margin:0;font:800 clamp(20px,2.6vw,26px)/1.1 var(--mmb-font);letter-spacing:-.01em;
    background:linear-gradient(176deg,var(--mmb-text) 22%,color-mix(in srgb,var(--mmb-text) 54%,var(--mmb-muted)));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
  .mmb-gate p{margin:0;color:var(--mmb-muted);font:400 13.5px/1.5 var(--mmb-font);max-width:340px}
  .mmb-signin{margin-top:6px;padding:12px 26px;border:none;border-radius:12px;cursor:pointer;color:#fff;font:700 14px/1 var(--mmb-font);
    background:linear-gradient(180deg,color-mix(in srgb,var(--mmb-info) 92%,#fff),var(--mmb-info));box-shadow:0 10px 28px -8px color-mix(in srgb,var(--mmb-info) 70%,transparent)}
  @media(max-width:560px){#mmb-panel,#mmb-panel.max,#mmb-panel.mmb-top{right:0;left:0;bottom:0;top:auto;margin:0;transform-origin:bottom center;transform:translateY(20px);width:100vw;height:88vh;border-radius:20px 20px 0 0}
    #mmb-panel.open{transform:none} .mmb-cards,#mmb-panel.max .mmb-cards{grid-template-columns:1fr}
    /* mobile is compact-only: no large mode (the overlay isn't responsive there) */
    .mmb-icon[data-act="max"]{display:none!important}
    #mmb-panel.max .mmb-rail,#mmb-panel.max .mmb-threads{display:none}
    /* iOS: composer font MUST be ≥16px or Safari zooms the viewport on focus */
    .mmb-ta{font-size:16px}
    /* no hardware modifier on a phone — the hint would be a lie AND a squeeze */
    .mmb-box.mmb-typing .mmb-hint{display:none}
    .mmb-comp{padding-bottom:calc(14px + env(safe-area-inset-bottom))}}
  /* follow-up suggestion chips (rendered under the latest reply) */
  .mmb-sugg{display:flex;flex-direction:column;align-items:flex-start;gap:6px;margin-top:8px}
  .mmb-sug{font:12.5px/1.35 var(--mmb-font);color:color-mix(in srgb,var(--mmb-text) 78%,var(--mmb-muted));background:color-mix(in srgb,var(--mmb-ink) 4%,transparent);border:1px solid var(--mmb-line);border-radius:12px;padding:7px 12px;text-align:left;cursor:pointer;max-width:100%;transition:border-color .16s var(--mmb-ease-tint),background .16s var(--mmb-ease-tint),color .16s var(--mmb-ease-tint),transform .16s var(--mmb-ease)}
  .mmb-sugg .mmb-sug{animation:mmb-rise .42s var(--mmb-ease) backwards;animation-delay:calc(var(--i,0)*70ms + 40ms)}
  .mmb-sug:hover{border-color:color-mix(in srgb,var(--mmb-info) 40%,transparent);background:color-mix(in srgb,var(--mmb-info) 8%,transparent);color:var(--mmb-text);transform:translateX(2px)}
  .mmb-sug:active{transform:translateX(2px) scale(.99)}
  .mmb-sug .g{color:var(--mmb-muted);margin-right:6px}
  /* "explain this panel" hover affordance on dashboard island cards */
  .mmb-exp{position:absolute;top:10px;right:10px;width:26px;height:26px;border-radius:50%;cursor:pointer;padding:0;
    background:var(--mmb-exp-bg);-webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px);
    border:1px solid var(--mmb-line);box-shadow:var(--mmb-exp-shadow);display:grid;place-items:center;opacity:0;pointer-events:none;transition:opacity .15s,border-color .15s,box-shadow .15s;z-index:5}
  .mmb-exp svg{width:12px;height:12px;fill:var(--mmb-exp-fg);opacity:.9}
  .sx:hover .mmb-exp{opacity:1;pointer-events:auto}
  .mmb-exp:hover{border-color:color-mix(in srgb,var(--mmb-info) 45%,transparent);box-shadow:0 0 12px -4px var(--mmb-info)}
  `;

  /* ── glyphs ── */
  var ORB = '<svg viewBox="0 0 24 24"><path d="M12 2l2.3 6.1L20.5 10l-6.2 1.9L12 18l-1.7-6.1L4 10l6.2-1.9z"/></svg>';
  /* solid star/orb path reused inside the explain-panel button (fill, no viewBox wrapper) */
  var ORB_PATH = 'M12 2l2.3 6.1L20.5 10l-6.2 1.9L12 18l-1.7-6.1L4 10l6.2-1.9z';
  var CLIP = '<svg viewBox="0 0 24 24"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></svg>';
  var CHECK = '<svg viewBox="0 0 24 24"><path d="M5 12.5l4 4 10-10"/></svg>';
  function ic(p) { return '<svg viewBox="0 0 24 24">' + p + '</svg>'; }

  /* ── depth marks ─────────────────────────────────────────────────────────────
     Fast, Pro and Deep Research are not three prices — they are three depths on ONE
     axis: how far down the desk goes for a single question. So they are drawn as a
     family rather than picked out of the emoji table (⚡ / ◈, which read as two
     unrelated stickers and rendered as somebody else's typeface on every OS):

       Fast      one strike — a single pass over the tape
       Pro       a cut stone — the same question turned to several faces
       Research  a descent — through the surface line and down two levels below it

     Fast/Pro are solid: at 12px a 1.8-stroke mark silts up, and these two are identity
     badges rather than affordances. Research keeps the outline language because it sits
     in the header among the outline icons. */
  var MARK_FAST = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M13.9 2 5 13.6h4.9L8.6 22l8.8-11.9h-4.9z"/></svg>';
  var MARK_PRO = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.3 20.5 9 12 21.7 3.5 9z"/>' +
    '<path class="fc" d="M3.5 9h17M12 2.3 9.1 9 12 21.7 14.9 9z"/></svg>';
  var MARK_RESEARCH = '<path d="M4.8 5.2h14.4"/><g class="dv"><path d="M8 10.1 12 13.9l4-3.8"/><path d="M8 15.3 12 19.1l4-3.8"/></g>';
  function laneMark(l) { return l === 'pro' ? MARK_PRO : MARK_FAST; }

  /* Ledger glyphs. PHASE_IC keys the pipeline stage the wire reports; FAM keys the KIND
     of source a step read. Both are picked from wire fields — never rendered from them. */
  var PHASE_IC = {
    start: '<path d="M4.5 6.5h15M4.5 12h15M4.5 17.5h8.5"/>',
    grounding: '<circle cx="12" cy="12" r="8.6"/><path d="M3.4 12h17.2M12 3.4c2.7 2.7 2.7 14.5 0 17.2"/>',
    model: '<path d="M6 4.2v6.3a3 3 0 0 0 3 3h8.4"/><path d="M14.6 10.6l3 2.9-3 2.9"/><path d="M6 19.8v-3.4"/>',
    synthesis: '<path d="M12 3.2 20 7.6 12 12 4 7.6z"/><path d="M4 12.6 12 17l8-4.4"/>',
    writing: '<path d="M4.2 19.8l3.4-.8L19.2 7.2a1.9 1.9 0 0 0-2.7-2.7L4.9 16.4z"/><path d="M14.6 6.4l2.9 2.9"/>',
    review: '<path d="M12 3.2l7.2 3v5.9c0 4.2-2.9 7.4-7.2 8.9-4.3-1.5-7.2-4.7-7.2-8.9V6.2z"/><path d="M9 12.1l2.3 2.3 4.2-4.4"/>'
  };
  var FAM = {
    tape: '<path d="M3.4 16.6l4.8-5.4 3.4 2.4L20.4 6"/><path d="M20.4 6h-4M20.4 6v4"/>',
    screen: '<path d="M3.6 5h16.8l-6.4 7.4V20l-4-2v-5.6z"/>',
    flow: '<path d="M3 13h3.4l2.2-6.4 3 12.6 2.3-6.2H21"/>',
    fund: '<path d="M5 19.6V9.4M12 19.6V4.4M19 19.6v-6.8"/><path d="M3 19.6h18"/>',
    book: '<path d="M5.4 4.4h13.2v15.2l-6.6-3.1-6.6 3.1z"/>',
    regime: '<circle cx="12" cy="12" r="8.6"/><path d="M15.4 8.6L13.2 13.2 8.6 15.4 10.8 10.8z"/>',
    theme: '<path d="M4.2 11.6 11.6 4.2l8.2 8.2-7.4 7.4z"/><circle cx="9" cy="9" r="1.3"/>',
    notes: '<path d="M6.2 3.6h8L18.6 8v12.4H6.2z"/><path d="M14.2 3.6V8h4.4M9 12.4h6M9 16h4"/>',
    chart: '<path d="M4.2 4.2v15.6h15.6"/><path d="M8.6 17v-5.2M12.6 17V7.6M16.6 17v-3.2"/>',
    check: '<path d="M7 8.4h9.6l-3-3"/><path d="M17 15.6H7.4l3 3"/>',
    data: '<path d="M12 5.2c4.4 0 8 1.2 8 2.6s-3.6 2.6-8 2.6-8-1.2-8-2.6 3.6-2.6 8-2.6z"/><path d="M4 7.8v8.4c0 1.4 3.6 2.6 8 2.6s8-1.2 8-2.6V7.8"/>'
  };
  /* The wire carries the raw tool `name` for the deployed widget's sake; it is NEVER
     rendered (leak law — the snake_case names the old widget printed ARE an internals
     leak). It is read here for ONE purpose: which family glyph a step wears, so twenty
     different reads resolve to a handful of legible marks. The regex tail catches tools
     that ship before this table is updated — a new read gets a plausible glyph, never a
     name on screen. */
  var TOOL_FAM = {
    get_quote: 'tape', get_symbol_context: 'tape', get_movers: 'tape', get_stage_peers: 'tape',
    screen_universe: 'screen',
    get_fundamentals: 'fund', get_earnings: 'fund',
    get_watchlist: 'book', get_portfolio_brief: 'book',
    get_smart_money: 'flow', get_insider_activity: 'flow', get_congress_trades: 'flow',
    read_options_entry_state: 'flow', explain_options_context: 'flow', query_options_confluence: 'flow',
    read_china_flows: 'flow', read_theme_trade_flows: 'flow', read_liquidity_plumbing: 'flow',
    get_house_view: 'regime', get_symbol_intel: 'regime', get_symbol_backtest: 'regime',
    read_world_state: 'regime', read_kernel: 'regime', read_graph: 'regime', query_spine: 'regime',
    read_cycle_pattern_state: 'regime', read_mechanism_pathways: 'regime', read_factor_state: 'regime',
    explain_factor_context: 'regime', read_stage_analysis: 'regime', read_china_decision_packet: 'regime',
    read_theme_state: 'theme', read_theme_thesis: 'theme', read_theme_pathways: 'theme',
    read_theme_asymmetry: 'theme', read_theme_options_witness: 'theme', read_theme_clinical: 'theme',
    get_market_events: 'notes', search_research: 'notes', context_search: 'notes',
    context_open: 'notes', read_artifact: 'notes', read_special_situations: 'notes',
    render_inline_chart: 'chart', annotate_chart: 'chart', chart_digest: 'chart',
    read_chart_state: 'chart', measure_line: 'chart', set_chart_symbol: 'chart',
    set_chart_timeframe: 'chart', toggle_chart_indicator: 'chart', run_chart_detection: 'chart',
    emit_chart_command: 'chart',
    read_contradictions: 'check', list_options_contradictions: 'check',
    list_factor_contradictions: 'check', read_governance: 'check'
  };
  function toolFam(name) {
    name = String(name || '');
    if (TOOL_FAM[name]) return TOOL_FAM[name];
    if (/chart|annotate|measure|indicator|detection/.test(name)) return 'chart';
    if (/contradict|governance/.test(name)) return 'check';
    if (/option|flow|smart_money|insider|congress/.test(name)) return 'flow';
    if (/theme/.test(name)) return 'theme';
    if (/research|context|artifact|event|news/.test(name)) return 'notes';
    if (/watchlist|portfolio/.test(name)) return 'book';
    if (/quote|price|mover|peer/.test(name)) return 'tape';
    if (/earning|fundamental/.test(name)) return 'fund';
    if (/screen/.test(name)) return 'screen';
    if (/^(read|query|get|explain)_/.test(name)) return 'regime';
    return 'data';
  }
  /* The second line under a running step. The server's label says WHAT it is doing; this
     says what KIND of question it is answering by doing it — the finer grain users asked
     for, still derived from the wire and still at "what kind of work" altitude. */
  var FAM_SUB = {
    tape:   ['checking what the tape actually did', '看盘面究竟走了什么'],
    screen: ['combing the market for matches', '在全市场里筛匹配的标的'],
    flow:   ['seeing which way the crowd is leaning', '看资金和仓位站在哪一边'],
    fund:   ['looking at the business underneath', '看背后的基本面'],
    book:   ['pulling up your own names', '调出你自己的持仓'],
    regime: ['placing this in the bigger picture', '把它放进大局里看'],
    theme:  ['following the theme it belongs to', '顺着它所属的主题看'],
    notes:  ['reading what is already written down', '翻看已有的研究记录'],
    chart:  ['working on the chart itself', '在图表上动手'],
    check:  ['making sure the readings agree', '核对各处读数是否一致'],
    data:   ['picking up one more read', '再取一份数据']
  };
  /* Rounds are not interchangeable: the first decides where to look, the second chases what
     the first turned up. Saying so is the difference between progress and a stuck line. */
  var MODEL_SUB = [
    ['working out where to look first', '先想清楚该从哪儿查起'],
    ['chasing what the first look turned up', '顺着第一轮的线索继续追'],
    ['tightening the read with one more pass', '再看一轮，把结论收紧']
  ];
  /* One plain clause per stage — what this part of the wait is FOR. The server owns the
     headline (bilingual, whitelisted); this is the widget's own second line, and it stays
     at "what kind of work" altitude: never how a signal is built. */
  var PHASE_SUB = {
    start: ["working out what you're really asking", '先弄清你真正想问的'],
    grounding: ["today's market state, before anything else", '先载入今日的市场状态'],
    model: ['deciding what to look up next', '决定接下来查什么'],
    synthesis: ['putting the pieces together', '把各条线索拼起来'],
    writing: ['turning it into plain words', '用平实的话写出来'],
    review: ["checking it against the desk's rules", '按台席规则复核']
  };

  /* ── DOM ─────────────────────────────────────────────────────────────── */
  var root = DOC.createElement('div');
  root.id = 'mmb-root';
  var st = DOC.createElement('style'); st.textContent = CSS; root.appendChild(st);

  var launchHtml = ANCHOR === 'br' ? (
    /* A div rather than a <button> because the pill collapses to a bare orb on phones and
       carries its own layout — so it is given a button's manners by hand: role + tab stop
       here, Enter/Space wired below, aria-expanded kept in sync by open()/close(). */
    '<div id="mmb-launch" role="button" tabindex="0" aria-expanded="false" aria-label="' + L('Ask Mastermind', '问操盘大脑') + '"><div class="mmb-orb">' + ORB + '</div>' +
    '<div class="lt"><span class="ll">' + LB('Ask Mastermind', '问操盘大脑') + '</span>' +
    '<span class="lk">' + LB('Brain · your desk copilot', '大脑 · 你的桌面副驾') + '</span></div></div>') : '';

  root.insertAdjacentHTML('beforeend', launchHtml +
    '<div id="mmb-scrim"></div>' +
    '<div id="mmb-panel"><div class="mmb-body">' +
      '<div class="mmb-rail"><div class="logo">' + ORB + '</div>' +
        '<button class="mmb-icon" data-act="new" title="New chat">' + ic('<path d="M12 5v14M5 12h14"/>') + '</button>' +
        '<button class="mmb-icon" data-act="search" title="Search">' + ic('<circle cx="11" cy="11" r="7"/><path d="M21 21l-4-4"/>') + '</button>' +
        '<button class="mmb-icon" data-act="home" title="Dashboard">' + ic('<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/>') + '</button>' +
        '<div class="sp"></div>' +
      '</div>' +
      '<div class="mmb-threads"><div class="mmb-th-h"><span>' + LB('Chats', '对话') + '</span></div>' +
        '<div class="mmb-search" id="mmb-search">' + ic('<circle cx="11" cy="11" r="7"/><path d="M21 21l-4-4"/>') +
          '<input id="mmb-search-in" type="text" autocomplete="off" data-ph-en="Search chats" data-ph-zh="搜索对话" placeholder="' + L('Search chats', '搜索对话') + '">' +
          '<button class="x" data-act="search-clear" title="Clear">' + ic('<path d="M6 6l12 12M18 6L6 18"/>') + '</button></div>' +
        '<div id="mmb-tlist"><div class="mmb-th-empty">' + L('Your conversations appear here.', '你的对话会显示在这里。') + '</div></div>' +
      '</div>' +
      '<div class="mmb-main"><div class="mmb-sidescrim" data-act="side"></div>' +
        '<div class="mmb-head">' +
          '<button class="mmb-icon mmb-menu" data-act="side" title="Chats">' + ic('<path d="M4 6h16M4 12h16M4 18h16"/>') + '</button>' +
          '<span class="ttl"><span class="dot"></span>' + LB('Mastermind Brain', '操盘大脑') + '</span>' +
          '<div class="sp"></div>' +
          '<button class="mmb-icon" data-act="max" title="Expand">' + ic('<path d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5"/>') + '</button>' +
          '<button class="mmb-icon" data-act="new" title="New chat">' + ic('<path d="M12 5v14M5 12h14"/>') + '</button>' +
          '<button class="mmb-icon" data-act="close" title="Close">' + ic('<path d="M6 6l12 12M18 6L6 18"/>') + '</button>' +
        '</div>' +
        '<div class="mmb-drop" id="mmb-drop" aria-hidden="true"><div class="mmb-drop-in">' +
          '<div class="mmb-drop-ic">' + ic('<rect x="3" y="4" width="18" height="14" rx="3"/><path d="M3 15l4.5-4.5 3.5 3.5 3-3L21 16"/><circle cx="9" cy="9" r="1.4"/>') + '</div>' +
          '<div class="mmb-drop-t">' + LB('Drop it here', '拖到这里') + '</div>' +
          '<div class="mmb-drop-s">' + LB('Charts, screenshots, anything you are looking at — I will read it.',
                                          '图表、截图、你正在看的任何画面 — 我来读。') + '</div>' +
        '</div></div>' +
        '<div class="mmb-scroll" id="mmb-scroll" role="log" aria-label="' + L('Conversation', '对话') + '" tabindex="0"></div>' +
        '<div id="mmb-live" class="mmb-sr" aria-live="polite" role="status"></div>' +
        '<div class="mmb-comp"><div class="mmb-upgrade" id="mmb-upgrade"></div>' +
          '<div class="mmb-box"><div class="mmb-ctx" id="mmb-ctx"></div>' +
            '<div class="mmb-thumbs" id="mmb-thumbs"></div>' +
            '<textarea class="mmb-ta" id="mmb-ta" rows="1" maxlength="2000" data-ph-en="Ask about any dashboard, signal, or ticker…" data-ph-zh="询问任意看板、信号或标的…" placeholder="' + L('Ask about any dashboard, signal, or ticker…', '询问任意看板、信号或标的…') + '"></textarea>' +
            '<input type="file" id="mmb-file" accept="image/png,image/jpeg,image/webp,image/gif" multiple hidden>' +
            '<div class="mmb-tools">' +
              /* ── one control, one axis ────────────────────────────────────────────
                 Fast, Pro and Deep Research are three stops on the same question —
                 how deep should the desk go — so they are one control, not a segmented
                 pair plus a pill parked in the header. Two things got better by moving
                 it: the three depth marks now read as the family they are, and the
                 header stopped truncating its own title ("Mastermin…") to make room. */
              '<div class="mmb-seg" id="mmb-lane" role="group" aria-label="' + L('Answer depth', '回答深度') + '">' +
                '<button data-lane="fast" class="on" aria-pressed="true">' + MARK_FAST + LB('Fast', '快速') + '</button>' +
                '<button data-lane="pro" aria-pressed="false">' + MARK_PRO + '<span>Pro</span></button>' +
                '<button class="mmb-rpill mmb-off" data-act="research" aria-pressed="false" aria-label="' + L('Deep Research', '深度研究') + '">' +
                  ic(MARK_RESEARCH) + LB('Deep', '深度') +
                  /* Tier-2 home for the mechanics (DESIGN_DOCTRINE §1): what the toggle
                     actually changes, in plain words, with its price stated rather than
                     discovered. aria-hidden + the aria-label above keep the accessible
                     name at "Deep Research" instead of a paragraph. */
                  '<span class="mmb-rtip" aria-hidden="true"><b>' + LB('A deeper pass on the same desk', '同一台席，更深的一遍') + '</b>' +
                  LB('It can look up around twice as many sources, then writes a structured read that ends on a clear stance.',
                     '可查阅约两倍的资料，并写成结构化研判，最后给出明确立场。') +
                  '<span class="cost">' + LB('Runs on Pro · uses one Pro message', '走 Pro 通道 · 消耗一条 Pro 消息') + '</span></span>' +
                '</button></div>' +
              /* aria-hidden: the send button's own label already says it — one announcement, not two */
              '<span class="mmb-hint" id="mmb-hint" aria-hidden="true">' + LB(SEND_KEYS + ' to send', SEND_KEYS + ' 发送') + '</span>' +
              '<div class="sp"></div>' +
              '<span class="mmb-q" id="mmb-q"></span>' +
              '<button class="mmb-tbtn" data-act="attach" title="Attach image">' + ic('<path d="M21 11.5l-8.5 8.5a5 5 0 0 1-7-7l8.5-8.5a3.5 3.5 0 0 1 5 5l-8.5 8.5a2 2 0 0 1-3-3l8-8"/>') + '</button>' +
              '<button class="mmb-tbtn" data-act="voice" title="Voice">' + ic('<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M6 11a6 6 0 0 0 12 0M12 17v4"/>') + '</button>' +
              '<button class="mmb-send" id="mmb-send" disabled>' + ic('<path d="M5 12h14M13 6l6 6-6 6"/>') + '</button>' +
            '</div></div>' +
        '</div>' +
      '</div>' +
    '</div></div>');
  DOC.body.appendChild(root);

  /* ── refs ── */
  var $ = function (s) { return root.querySelector(s); };
  var scrim = $('#mmb-scrim'), panel = $('#mmb-panel'), scroll = $('#mmb-scroll'),
      ta = $('#mmb-ta'), sendBtn = $('#mmb-send'), qEl = $('#mmb-q'), ctxEl = $('#mmb-ctx'),
      upgradeEl = $('#mmb-upgrade'), tlist = $('#mmb-tlist'), launch = $('#mmb-launch'),
      researchBtn = $('.mmb-rpill'), thumbsEl = $('#mmb-thumbs'), fileEl = $('#mmb-file'),
      searchWrap = $('#mmb-search'), searchIn = $('#mmb-search-in'), boxEl = $('.mmb-box');

  /* ── state ── */
  var lane = 'fast', researchMode = false, threadId = null, streaming = false,
      quotas = {}, authed = false, guestMode = false, ctxSymbol = '', streamAbort = null, pendingImages = [], proEligible = false;
  var MAX_IMAGES = 4;
  var explainPanel = null; /* set by MMBrain.explain(); attached once to the next send()'s context */

  function esc(s) { var d = DOC.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; }
  function el(tag, cls) { var e = DOC.createElement(tag); if (cls) e.className = cls; return e; }

  /* ── Markdown engine (GFM-lite, DOM-only) ──────────────────────────────────
     Every node is built with createElement/textContent — model text NEVER touches
     innerHTML, so injection is impossible by construction. The SAME functions render
     streamed CLOSED blocks, the final done re-render, and loaded history — so a reply
     looks byte-identical whether it streamed live or was rehydrated from a thread. */

  /* inline: **bold**, *italic*, `code`, [text](url) (https/http only). Appends to `parent`. */
  var MD_INLINE = /(\*\*([^*]+)\*\*)|(\*([^*\n]+)\*)|(`([^`]+)`)|(\[([^\]]+)\]\((https?:\/\/[^\s)]+)\))/;
  function mdInline(parent, text) {
    text = String(text == null ? '' : text);
    var m;
    while (text && (m = MD_INLINE.exec(text))) {
      if (m.index > 0) parent.appendChild(DOC.createTextNode(text.slice(0, m.index)));
      if (m[1]) { var b = el('strong'); b.textContent = m[2]; parent.appendChild(b); }
      else if (m[3]) { var it = el('em'); it.textContent = m[4]; parent.appendChild(it); }
      else if (m[5]) { var c = el('code'); c.textContent = m[6]; parent.appendChild(c); }
      else if (m[7]) { var a = el('a'); a.textContent = m[8]; a.href = m[9]; a.target = '_blank'; a.rel = 'noopener noreferrer'; parent.appendChild(a); }
      text = text.slice(m.index + m[0].length);
    }
    if (text) parent.appendChild(DOC.createTextNode(text));
    return parent;
  }
  function isTableSep(ln) { return /^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$/.test(ln) && ln.indexOf('-') !== -1 && ln.indexOf('|') !== -1; }
  function splitRow(ln) {
    var s = ln.trim().replace(/^\|/, '').replace(/\|$/, '');
    return s.split('|').map(function (c) { return c.trim(); });
  }
  /* Render ONE closed block's text into a DOM node (or null for blank). */
  function mdBlock(block) {
    var lines = block.replace(/\s+$/, '').split('\n');
    var first = lines[0] || '';
    /* fenced code — caller passes the whole ```…``` block including fences */
    var fence = first.match(/^```(\S*)/);
    if (fence) {
      var wrap = el('div', 'mmb-code');
      var lang = fence[1] || '';
      var bar = el('div', 'mmb-code-bar');
      var lab = el('span', 'mmb-code-lang'); lab.textContent = lang || 'code'; bar.appendChild(lab);
      var cp = el('button', 'mmb-code-copy'); cp.type = 'button'; cp.title = 'Copy code'; cp.setAttribute('aria-label', L('Copy code', '复制代码')); cp.textContent = L('Copy', '复制'); bar.appendChild(cp);
      var body = lines.slice(1);
      if (body.length && /^```/.test(body[body.length - 1])) body = body.slice(0, -1);
      var pre = el('pre'); var code = el('code'); code.textContent = body.join('\n'); pre.appendChild(code);
      cp.addEventListener('click', function (e) {
        e.stopPropagation();
        try { if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(code.textContent).then(function () { cp.textContent = L('Copied', '已复制'); setTimeout(function () { cp.textContent = L('Copy', '复制'); }, 1200); }).catch(function () {}); } catch (e2) {}
      });
      wrap.appendChild(bar); wrap.appendChild(pre); return wrap;
    }
    /* horizontal rule */
    if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(block)) return el('hr', 'mmb-hr');
    /* table — needs a header row + a separator line under it */
    if (lines.length >= 2 && first.indexOf('|') !== -1 && isTableSep(lines[1])) {
      var tbl = el('table', 'mmb-table');
      var thead = el('thead'), htr = el('tr');
      splitRow(first).forEach(function (c) { var th = el('th'); mdInline(th, c); htr.appendChild(th); });
      thead.appendChild(htr); tbl.appendChild(thead);
      var tb = el('tbody');
      for (var r = 2; r < lines.length; r++) {
        if (!lines[r].trim()) continue;
        var tr = el('tr');
        splitRow(lines[r]).forEach(function (c) { var td = el('td'); mdInline(td, c); tr.appendChild(td); });
        tb.appendChild(tr);
      }
      tbl.appendChild(tb); return tbl;
    }
    /* blockquote */
    if (/^\s*>\s?/.test(first)) {
      var bq = el('blockquote', 'mmb-bq');
      var qt = lines.map(function (l) { return l.replace(/^\s*>\s?/, ''); }).join('\n');
      mdInline(bq, qt); return bq;
    }
    /* heading — ## → h4, ###+ → h5 */
    var hm = first.match(/^(#{2,6})\s+(.*)/);
    if (hm && lines.length === 1) { var h = el(hm[1].length <= 2 ? 'h4' : 'h5'); mdInline(h, hm[2]); return h; }
    /* ordered list */
    if (/^\s*\d+\.\s+/.test(first)) {
      var ol = el('ol');
      lines.forEach(function (l) { var mm = l.match(/^\s*\d+\.\s+(.*)/); if (mm) { var li = el('li'); mdInline(li, mm[1]); ol.appendChild(li); } });
      if (ol.childNodes.length) return ol;
    }
    /* bullet list */
    if (/^\s*[-*•]\s+/.test(first)) {
      var ul = el('ul');
      lines.forEach(function (l) { var mm = l.match(/^\s*[-*•]\s+(.*)/); if (mm) { var li = el('li'); mdInline(li, mm[1]); ul.appendChild(li); } });
      if (ul.childNodes.length) return ul;
    }
    /* paragraph (soft line breaks preserved) */
    if (!block.trim()) return null;
    var p = el('p');
    lines.forEach(function (l, i) { if (i) p.appendChild(el('br')); mdInline(p, l); });
    return p;
  }
  /* line kind for block-boundary detection: list item, heading, quote, or 'text'.
     A change of kind starts a new block even without a blank line — models routinely
     omit the blank between a lead-in sentence and its bullet list. */
  function lineKind(ln) {
    if (/^\s*([-*•]|\d+\.)\s+/.test(ln)) return 'list';
    if (/^\s*#{1,6}\s+/.test(ln)) return 'head';
    if (/^\s*>\s?/.test(ln)) return 'quote';
    if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(ln)) return 'rule';
    return 'text';
  }
  /* Split raw markdown into block strings on blank lines, respecting ``` fences and
     kind transitions. A fenced block stays whole even across blanks. Returns block texts. */
  function mdSplit(text) {
    var lines = String(text || '').split('\n'), blocks = [], cur = [], inFence = false, curKind = null;
    function push() { if (cur.length) { blocks.push(cur.join('\n')); cur = []; curKind = null; } }
    for (var i = 0; i < lines.length; i++) {
      var ln = lines[i];
      if (/^```/.test(ln)) {
        if (!inFence) { push(); inFence = true; cur.push(ln); }
        else { cur.push(ln); push(); inFence = false; }
        continue;
      }
      if (inFence) { cur.push(ln); continue; }
      if (!ln.trim()) { push(); continue; }
      var k = lineKind(ln);
      /* break when kind changes (text→list, list→text, heading→anything, etc.); a heading
         and a rule are always solo blocks so they never absorb a following line */
      if (cur.length && (k !== curKind || curKind === 'head' || curKind === 'rule' || k === 'head' || k === 'rule')) push();
      cur.push(ln); curKind = k;
    }
    push(); return blocks;
  }
  /* Full render of `text` into `container` (cleared first). History + final correctness. */
  function renderMdInto(container, text) {
    container.textContent = '';
    mdSplit(text).forEach(function (blk) { var node = mdBlock(blk); if (node) container.appendChild(node); });
    return container;
  }
  /* Kept name (history load, non-stream). Routes through the same engine → returns a
     DocumentFragment so callers can append without ever touching innerHTML. */
  function renderMd(text) {
    var frag = DOC.createDocumentFragment();
    mdSplit(text).forEach(function (blk) { var node = mdBlock(blk); if (node) frag.appendChild(node); });
    return frag;
  }

  /* ── MdStream: append-only incremental renderer + smooth-reveal writer ────────
     Owned per assistant message. `push(chunk)` accumulates raw text into a buffer that
     one rAF loop drains into the visible text at a typed pace. CLOSED blocks (a blank
     line closed them) render ONCE into permanent DOM and are never touched again. The
     OPEN (last) block streams as plain-text `mmb-ink` fade spans while it grows, then
     converts to parsed DOM the moment it closes. `finalize()` re-renders the whole raw
     string through renderMdInto for correctness (bold/links in the last block, any open
     table). Injection-proof: only textContent + createElement, never innerHTML. */
  function MdStream(container) {
    var raw = '';               // full accumulated markdown (source of truth)
    var pending = '';           // drained-pending chars not yet revealed
    var revealed = '';          // chars already shown
    var committedLen = 0;       // length of `revealed` already turned into CLOSED block DOM
    var openText = null;        // the live text node for the currently-open block
    var caret = null;
    var raf = 0, doneFlush = false, onDrained = null;
    var reduced = reduceMotion();

    function ensureOpenText() {
      if (openText && openText.parentNode) return openText;
      openText = el('div', 'mmb-blk mmb-open');
      container.appendChild(openText);
      if (caret) container.appendChild(caret);   // caret trails the open block
      return openText;
    }
    // Render everything in `revealed` after committedLen: commit any newly-closed blocks
    // as permanent DOM, then (re)draw the trailing open block as plain text + fade span.
    function paint(freshChunk) {
      var tail = revealed.slice(committedLen);
      // find the last blank-line boundary that is NOT inside an open fence
      var fences = (tail.match(/```/g) || []).length;
      var openFence = (fences % 2) === 1;
      var lastBlank = -1;
      if (!openFence) {
        var mBlank = /\n[ \t]*\n/g, mm;
        while ((mm = mBlank.exec(tail))) lastBlank = mm.index + mm[0].length;
      }
      if (lastBlank > 0) {
        var closedText = tail.slice(0, lastBlank);
        mdSplit(closedText).forEach(function (blk) { var node = mdBlock(blk); if (node) { node.classList && node.classList.add('mmb-blk'); container.insertBefore(node, openText); } });
        committedLen += closedText.length;
        if (openText) { openText.parentNode && openText.parentNode.removeChild(openText); openText = null; }
        tail = revealed.slice(committedLen);
      }
      // draw the (possibly reset) open block as plain streaming text
      var node2 = ensureOpenText();
      var priorLen = node2.textContent.length;
      var full = tail;
      if (full.length < priorLen || full.slice(0, priorLen) !== node2.textContent) {
        // block reset or diverged — rebuild plain
        node2.textContent = full;
      } else if (full.length > priorLen) {
        var add = full.slice(priorLen);
        if (reduced || !freshChunk) { node2.appendChild(DOC.createTextNode(add)); }
        else { var ink = el('span', 'mmb-ink'); ink.textContent = add; node2.appendChild(ink); }
      }
    }
    function tick() {
      raf = 0;
      if (!pending.length) {
        if (doneFlush) { doneFlush = false; if (onDrained) { var cb = onDrained; onDrained = null; cb(); } }
        return;
      }
      var backlog = pending.length;
      var factor = doneFlush ? 0.72 : 0.12;   // ×6 catch-up on done
      var n = Math.max(2, Math.min(48, Math.round(backlog * factor)));
      if (doneFlush) n = Math.max(n, Math.min(backlog, 96));
      var chunk = pending.slice(0, n); pending = pending.slice(n);
      revealed += chunk;
      paint(true);
      if (streaming || pending.length || doneFlush) stickAfter();
      raf = requestAnimationFrame(tick);
    }
    function schedule() { if (!raf) raf = requestAnimationFrame(tick); }

    return {
      startCaret: function () {
        if (reduced || caret) return;
        caret = el('span', 'mmb-caret'); container.appendChild(caret);
      },
      push: function (chunk) {
        if (!chunk) return;
        raw += chunk;
        if (reduced) { revealed += chunk; paint(false); stickAfter(); return; }
        pending += chunk; schedule();
      },
      raw: function () { return raw; },
      // drain fast then run cb, then full re-render for correctness
      finalize: function (cb) {
        var done = false;
        var finish = function () {
          if (done) return; done = true;
          if (safety) { clearTimeout(safety); safety = 0; }
          if (raf) { cancelAnimationFrame(raf); raf = 0; }
          renderMdInto(container, raw);
          revealed = raw; committedLen = raw.length; pending = ''; openText = null; doneFlush = false;
          if (caret) { caret.parentNode && caret.parentNode.removeChild(caret); caret = null; }
          if (cb) cb();
        };
        if (reduced || !pending.length) { revealed += pending; pending = ''; finish(); return; }
        doneFlush = true; onDrained = finish; schedule();
        /* rAF-independent safety net: if the smooth drain stalls (e.g. the tab is hidden
           and requestAnimationFrame is throttled to zero), force the final render anyway
           so a completed reply is never left blank. */
        var safety = setTimeout(finish, 1400);
      },
      // stop: keep partial, drop caret, no re-render (partial stays as-is)
      stop: function () {
        if (raf) { cancelAnimationFrame(raf); raf = 0; }
        revealed += pending; pending = ''; doneFlush = false;
        paint(false);
        if (caret) { caret.parentNode && caret.parentNode.removeChild(caret); caret = null; }
      },
      cancel: function () { if (raf) { cancelAnimationFrame(raf); raf = 0; } if (caret) { caret.parentNode && caret.parentNode.removeChild(caret); caret = null; } }
    };
  }

  /* ══ in-chat chart engine ══════════════════════════════════════════════════════
     The gateway's render_inline_chart hands back a picture produced by the SOCIAL-POST
     renderer — watermark, logo, CTA, flat black, a price axis you cannot read and a MACD
     squeezed into a strip. That engine is right for an image posted to a timeline and
     wrong for a reply: here the user is looking at a chart, not receiving one.

     So the widget draws its own from the same daily bars the site publishes
     (<store>/<TICKER>.json on the data plane), and keeps the server SVG only as the
     fallback for symbols it has no bars for. Everything below is computed client-side:
     EMA20 / SMA50 / RSI(14) / MACD(12,26,9) over the FULL history, then the last window
     is drawn — so no indicator starts mid-canvas the way a warm-up-less render does.

     Nothing here is a signal. It draws the bars the desk already publishes; the read
     stays in the model's words underneath.  ────────────────────────────────────────── */
  var SVGNS = 'http://www.w3.org/2000/svg';
  /* Per-market stores, mirroring the data-plane prefixes in data_base.js. A suffix picks
     the store; unknown suffixes take the US store and simply miss (→ server fallback). */
  function chartStore(t) {
    t = String(t || '').toUpperCase();
    if (/\.(SS|SZ|SH)$/.test(t)) return 'chinaohlc';
    if (/\.HK$/.test(t)) return 'hkohlc';
    if (/\.(TO|V|CN|NE)$/.test(t)) return 'canadaohlc';
    if (/\.(T|KS|KQ|TW|TWO|L|DE|PA|AS|MI|MC|SW|ST|HE|OL|CO|AX|NZ|SI|BO|NS)$/.test(t)) return 'intlohlc';
    return 'ohlc';
  }
  /* The dashboard rewrites relative store paths to the data plane via its own fetch shim;
     the Terminal has no shim, so the base is resolved explicitly. CFG wins, then the host
     page's DATA_BASE, then the public data plane this widget is served alongside. */
  var DATA_FALLBACK = 'https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev';
  function chartBase() {
    var b = CFG.dataBase || window.DATA_BASE || DATA_FALLBACK;
    return String(b).replace(/\/+$/, '');
  }
  var barCache = {};
  function fetchBars(ticker) {
    var key = String(ticker || '').toUpperCase();
    if (barCache[key]) return barCache[key];
    var url = chartBase() + '/' + chartStore(key) + '/' + encodeURIComponent(key) + '.json';
    barCache[key] = fetch(url, { credentials: 'omit' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        var bars = d && d.bars;
        if (!bars || !bars.length) return null;
        /* [date, o, h, l, c, v] — reject rows that are not a full OHLC bar rather than
           drawing a candle out of nulls. */
        var out = [];
        for (var i = 0; i < bars.length; i++) {
          var b = bars[i];
          if (!b || b.length < 5) continue;
          var o = +b[1], h = +b[2], lo = +b[3], c = +b[4];
          if (!isFinite(o) || !isFinite(h) || !isFinite(lo) || !isFinite(c)) continue;
          out.push({ d: String(b[0]), o: o, h: h, l: lo, c: c, v: isFinite(+b[5]) ? +b[5] : 0 });
        }
        return out.length >= 30 ? out : null;
      })
      .catch(function () { return null; });
    return barCache[key];
  }

  /* ── indicator math (full-history, so the visible window is always warm) ── */
  function emaSeries(v, n) {
    var k = 2 / (n + 1), out = new Array(v.length), prev = null;
    for (var i = 0; i < v.length; i++) {
      prev = prev === null ? v[i] : v[i] * k + prev * (1 - k);
      out[i] = i >= n - 1 ? prev : null;
    }
    return out;
  }
  function smaSeries(v, n) {
    var out = new Array(v.length), sum = 0;
    for (var i = 0; i < v.length; i++) {
      sum += v[i];
      if (i >= n) sum -= v[i - n];
      out[i] = i >= n - 1 ? sum / n : null;
    }
    return out;
  }
  function rsiSeries(v, n) {
    var out = new Array(v.length), g = 0, l = 0, i;
    for (i = 1; i <= n && i < v.length; i++) { var d = v[i] - v[i - 1]; if (d >= 0) g += d; else l -= d; }
    var ag = g / n, al = l / n;
    for (i = 0; i < v.length; i++) out[i] = null;
    if (v.length > n) out[n] = al === 0 ? 100 : 100 - 100 / (1 + ag / al);
    for (i = n + 1; i < v.length; i++) {
      var ch = v[i] - v[i - 1];
      ag = (ag * (n - 1) + (ch > 0 ? ch : 0)) / n;
      al = (al * (n - 1) + (ch < 0 ? -ch : 0)) / n;
      out[i] = al === 0 ? 100 : 100 - 100 / (1 + ag / al);
    }
    return out;
  }
  function macdSeries(v) {
    var f = emaSeries(v, 12), s = emaSeries(v, 26), line = [], i;
    for (i = 0; i < v.length; i++) line[i] = (f[i] === null || s[i] === null) ? null : f[i] - s[i];
    /* the signal EMA runs on the MACD line's own defined stretch, not on nulls */
    var start = 0; while (start < line.length && line[start] === null) start++;
    var sig = new Array(v.length), k = 2 / 10, prev = null;
    for (i = 0; i < v.length; i++) sig[i] = null;
    for (i = start; i < line.length; i++) {
      prev = prev === null ? line[i] : line[i] * k + prev * (1 - k);
      if (i - start >= 8) sig[i] = prev;
    }
    var hist = new Array(v.length);
    for (i = 0; i < v.length; i++) hist[i] = (line[i] === null || sig[i] === null) ? null : line[i] - sig[i];
    return { line: line, signal: sig, hist: hist };
  }

  /* ── small helpers ── */
  function svgEl(tag, attrs) {
    var e = DOC.createElementNS(SVGNS, tag);
    if (attrs) for (var k in attrs) if (attrs[k] !== null && attrs[k] !== undefined) e.setAttribute(k, attrs[k]);
    return e;
  }
  function niceStep(range, target) {
    var raw = range / Math.max(1, target), mag = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10));
    var norm = raw / mag;
    var step = norm >= 5 ? 10 : norm >= 2.5 ? 5 : norm >= 2 ? 2.5 : norm >= 1 ? 2 : 1;
    return step * mag;
  }
  function fmtPrice(v) {
    var a = Math.abs(v);
    if (a >= 1000) return v.toFixed(0);
    if (a >= 100) return v.toFixed(1);
    if (a >= 1) return v.toFixed(2);
    return v.toFixed(4);
  }
  function fmtVol(v) {
    if (v >= 1e9) return (v / 1e9).toFixed(1) + 'B';
    if (v >= 1e6) return (v / 1e6).toFixed(1) + 'M';
    if (v >= 1e3) return (v / 1e3).toFixed(0) + 'K';
    return String(Math.round(v));
  }
  var MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  var MON_ZH = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'];
  function monLabel(iso) {
    var p = String(iso).split('-'); var m = (+p[1] || 1) - 1;
    return (zh() ? MON_ZH : MON)[m] + (m === 0 ? " '" + String(p[0]).slice(2) : '');
  }

  /* ── the renderer ────────────────────────────────────────────────────────────
     One pass builds the whole SVG; the animation is CSS on the pieces, so a resize or a
     theme flip is a plain re-render and never a half-played sequence. */
  function drawChart(box, ticker, tf, bars) {
    var reduced = reduceMotion();
    var W = Math.max(280, Math.min(1100, Math.round(box.clientWidth || 420)));
    var H = Math.round(Math.max(330, Math.min(560, W * 0.72)));
    var PAD_R = 54, PAD_L = 8, X0 = PAD_L, X1 = W - PAD_R;
    var plotW = X1 - X0;
    /* one bar every ~6.4px, so a wide panel shows more history instead of fatter candles */
    var VIS = Math.max(52, Math.min(200, Math.floor(plotW / 5.6)));
    var TOP = 10, XAXIS = 20;
    var priceH = Math.round((H - TOP - XAXIS) * 0.62);
    var rsiH = Math.round((H - TOP - XAXIS) * 0.14);
    var macdH = (H - TOP - XAXIS) - priceH - rsiH - 16;
    var pY0 = TOP, pY1 = TOP + priceH;
    var rY0 = pY1 + 8, rY1 = rY0 + rsiH;
    var mY0 = rY1 + 8, mY1 = mY0 + macdH;

    var close = bars.map(function (b) { return b.c; });
    var ema20 = emaSeries(close, 20), sma50 = smaSeries(close, 50);
    var rsi = rsiSeries(close, 14), mac = macdSeries(close);

    var i0 = Math.max(0, bars.length - VIS);
    var view = bars.slice(i0), n = view.length;
    var step = plotW / n, cw = Math.max(1.5, Math.min(11, step * 0.66));
    function cx(k) { return X0 + step * (k + 0.5); }

    /* price scale spans the bars AND the overlays, so a moving average never leaves the pane */
    var lo = Infinity, hi = -Infinity, k;
    for (k = 0; k < n; k++) { if (view[k].l < lo) lo = view[k].l; if (view[k].h > hi) hi = view[k].h; }
    for (k = i0; k < bars.length; k++) {
      if (ema20[k] !== null) { lo = Math.min(lo, ema20[k]); hi = Math.max(hi, ema20[k]); }
      if (sma50[k] !== null) { lo = Math.min(lo, sma50[k]); hi = Math.max(hi, sma50[k]); }
    }
    var padY = (hi - lo) * 0.07 || 1;
    lo -= padY; hi += padY;
    function py(v) { return pY1 - (v - lo) / (hi - lo) * (pY1 - pY0); }

    var svg = svgEl('svg', { viewBox: '0 0 ' + W + ' ' + H, width: W, height: H,
                             preserveAspectRatio: 'xMidYMid meet', role: 'img' });
    svg.setAttribute('aria-label', ticker + ' ' + (tf || 'daily') + ' price chart');
    var GRID = 'color-mix(in srgb, var(--mmb-cx-grid) 9%, transparent)';
    var AXIS = 'var(--mmb-muted)';
    function delay(ms) { return reduced ? null : ms + 'ms'; }

    /* ── grid + price axis ── */
    var gGrid = svgEl('g', { class: reduced ? '' : 'fade' });
    if (!reduced) gGrid.style.animationDelay = '60ms';
    var pstep = niceStep(hi - lo, 5);
    var first = Math.ceil(lo / pstep) * pstep;
    for (var pv = first; pv < hi; pv += pstep) {
      var yy = py(pv);
      gGrid.appendChild(svgEl('line', { x1: X0, x2: X1, y1: yy, y2: yy, stroke: GRID, 'stroke-width': 1 }));
      var tl = svgEl('text', { x: X1 + 7, y: yy + 3.4, fill: AXIS, 'font-size': 10,
                               'font-family': 'ui-monospace,SFMono-Regular,Menlo,monospace' });
      tl.textContent = fmtPrice(pv);
      gGrid.appendChild(tl);
    }
    svg.appendChild(gGrid);

    /* ── volume, sunk into the bottom third of the price pane ── */
    var vmax = 0;
    for (k = 0; k < n; k++) if (view[k].v > vmax) vmax = view[k].v;
    var volTop = pY1 - (pY1 - pY0) * 0.20;
    var gVol = svgEl('g', { opacity: .34 });
    for (k = 0; k < n && vmax > 0; k++) {
      var vh = Math.max(0.6, (view[k].v / vmax) * (pY1 - volTop));
      var vb = svgEl('rect', { x: cx(k) - cw / 2, y: pY1 - vh, width: cw, height: vh,
                               fill: view[k].c >= view[k].o ? 'var(--mmb-up)' : 'var(--mmb-dn)',
                               class: reduced ? '' : 'vbar', rx: .5 });
      if (!reduced) vb.style.animationDelay = (120 + k * (620 / n)) + 'ms';
      gVol.appendChild(vb);
    }
    svg.appendChild(gVol);

    /* ── candles ── */
    var gC = svgEl('g');
    for (k = 0; k < n; k++) {
      var b = view[k], up = b.c >= b.o, col = up ? 'var(--mmb-up)' : 'var(--mmb-dn)';
      var g1 = svgEl('g', { class: reduced ? '' : 'cndl' });
      if (!reduced) g1.style.animationDelay = (110 + k * (640 / n)) + 'ms';
      g1.appendChild(svgEl('line', { x1: cx(k), x2: cx(k), y1: py(b.h), y2: py(b.l),
                                     stroke: col, 'stroke-width': Math.max(1, cw * 0.16) }));
      var yTop = py(Math.max(b.o, b.c)), bodyH = Math.max(1, Math.abs(py(b.o) - py(b.c)));
      g1.appendChild(svgEl('rect', { x: cx(k) - cw / 2, y: yTop, width: cw, height: bodyH,
                                     fill: col, rx: Math.min(1.5, cw * 0.2) }));
      gC.appendChild(g1);
    }
    svg.appendChild(gC);

    /* ── overlays: EMA20 + SMA50, drawn rather than pasted ── */
    function linePath(series, color, width, dash, delayMs, klass) {
      var d = '', started = false;
      for (var j = 0; j < n; j++) {
        var v = series[i0 + j];
        if (v === null || v === undefined) { started = false; continue; }
        d += (started ? 'L' : 'M') + cx(j).toFixed(1) + ' ' + py(v).toFixed(1) + ' ';
        started = true;
      }
      if (!d) return null;
      var p = svgEl('path', { d: d, fill: 'none', stroke: color, 'stroke-width': width,
                              'stroke-linecap': 'round', 'stroke-linejoin': 'round',
                              class: klass || '' });
      if (dash) p.setAttribute('stroke-dasharray', dash);
      if (!reduced && !dash) {
        svg.appendChild(p);
        var L = 0; try { L = p.getTotalLength(); } catch (e) { L = 0; }
        if (L) {
          p.style.setProperty('--len', L);
          p.setAttribute('stroke-dasharray', L);
          p.classList.add('draw');
          p.style.animationDelay = delayMs + 'ms';
        }
        return p;
      }
      return p;
    }
    var pe = linePath(ema20, 'var(--mmb-info)', 1.5, null, 380);
    if (pe && !pe.parentNode) svg.appendChild(pe);
    var ps = linePath(sma50, 'var(--mmb-violet)', 1.5, null, 520);
    if (ps && !ps.parentNode) svg.appendChild(ps);

    /* ── last-price tag on the axis ── */
    var lastBar = view[n - 1], lastY = py(lastBar.c);
    var tag = svgEl('g', { class: reduced ? '' : 'pop' });
    if (!reduced) tag.style.animationDelay = '900ms';
    var tagCol = lastBar.c >= lastBar.o ? 'var(--mmb-up)' : 'var(--mmb-dn)';
    tag.appendChild(svgEl('line', { x1: X0, x2: X1, y1: lastY, y2: lastY, stroke: tagCol,
                                    'stroke-width': 1, 'stroke-dasharray': '2 3', opacity: .55 }));
    tag.appendChild(svgEl('rect', { x: X1 + 2, y: lastY - 8, width: PAD_R - 6, height: 16, rx: 4, fill: tagCol }));
    var tt = svgEl('text', { x: X1 + 5, y: lastY + 3.6, fill: '#fff', 'font-size': 10, 'font-weight': 700,
                             'font-family': 'ui-monospace,SFMono-Regular,Menlo,monospace' });
    tt.textContent = fmtPrice(lastBar.c);
    tag.appendChild(tt);
    svg.appendChild(tag);

    /* ── RSI pane ── */
    function paneLabel(y, txt, extra) {
      /* a legend CHIP, not bare text: an unbacked label sits directly on the RSI line and
         both become unreadable where they cross. */
      var g = svgEl('g', { class: reduced ? '' : 'fade' });
      var w = txt.length * 5.1 + 10;
      g.appendChild(svgEl('rect', { x: X0 + 1, y: y + 1.5, width: w, height: 12, rx: 3,
                                    fill: 'var(--mmb-cx-b)', opacity: .72 }));
      var t = svgEl('text', { x: X0 + 6, y: y + 10.4, fill: AXIS, 'font-size': 9,
                              'font-weight': 700, 'letter-spacing': .35,
                              'font-family': 'ui-monospace,SFMono-Regular,Menlo,monospace' });
      t.textContent = txt;
      g.appendChild(t);
      if (!reduced) g.style.animationDelay = (extra || 700) + 'ms';
      return g;
    }
    var gR = svgEl('g');
    gR.appendChild(svgEl('rect', { x: X0, y: rY0 + (rY1 - rY0) * 0.3, width: plotW, height: (rY1 - rY0) * 0.4,
                                   fill: GRID, opacity: .6 }));
    function ry(v) { return rY1 - (v / 100) * (rY1 - rY0); }
    var prsi = '', st = false;
    for (k = 0; k < n; k++) {
      var rv = rsi[i0 + k];
      if (rv === null || rv === undefined) { st = false; continue; }
      prsi += (st ? 'L' : 'M') + cx(k).toFixed(1) + ' ' + ry(rv).toFixed(1) + ' '; st = true;
    }
    if (prsi) {
      var rp = svgEl('path', { d: prsi, fill: 'none', stroke: 'var(--mmb-info)', 'stroke-width': 1.4,
                               'stroke-linejoin': 'round' });
      gR.appendChild(rp);
      if (!reduced) {
        svg.appendChild(gR);
        var RL = 0; try { RL = rp.getTotalLength(); } catch (e2) { RL = 0; }
        if (RL) { rp.style.setProperty('--len', RL); rp.setAttribute('stroke-dasharray', RL); rp.classList.add('draw'); rp.style.animationDelay = '760ms'; }
      }
    }
    gR.appendChild(paneLabel(rY0, 'RSI 14', 720));
    var rlast = rsi[bars.length - 1];
    if (rlast !== null && rlast !== undefined) {
      var rt = svgEl('text', { x: X1 + 7, y: ry(rlast) + 3.4, fill: AXIS, 'font-size': 10,
                               'font-family': 'ui-monospace,SFMono-Regular,Menlo,monospace',
                               class: reduced ? '' : 'fade' });
      rt.textContent = rlast.toFixed(0);
      if (!reduced) rt.style.animationDelay = '860ms';
      gR.appendChild(rt);
    }
    if (!gR.parentNode) svg.appendChild(gR);

    /* ── MACD pane: histogram + both lines, on its own scale ── */
    var gM = svgEl('g');
    var mlo = Infinity, mhi = -Infinity;
    for (k = i0; k < bars.length; k++) {
      [mac.line[k], mac.signal[k], mac.hist[k]].forEach(function (v) {
        if (v === null || v === undefined) return;
        if (v < mlo) mlo = v; if (v > mhi) mhi = v;
      });
    }
    if (!isFinite(mlo)) { mlo = -1; mhi = 1; }
    var mspan = Math.max(Math.abs(mlo), Math.abs(mhi)) * 1.12 || 1;
    function my(v) { return (mY0 + mY1) / 2 - (v / mspan) * ((mY1 - mY0) / 2); }
    gM.appendChild(svgEl('line', { x1: X0, x2: X1, y1: my(0), y2: my(0), stroke: GRID, 'stroke-width': 1 }));
    for (k = 0; k < n; k++) {
      var hv = mac.hist[i0 + k];
      if (hv === null || hv === undefined) continue;
      var y0 = my(0), y1 = my(hv), hh = Math.max(0.8, Math.abs(y1 - y0));
      var hb = svgEl('rect', { x: cx(k) - cw / 2, y: Math.min(y0, y1), width: cw, height: hh, rx: .5,
                               fill: hv >= 0 ? 'var(--mmb-up)' : 'var(--mmb-dn)', opacity: .55,
                               class: reduced ? '' : 'hbar' });
      if (!reduced) hb.style.animationDelay = (700 + k * (420 / n)) + 'ms';
      gM.appendChild(hb);
    }
    function macdPath(series, color, w, delayMs) {
      var d = '', started = false;
      for (var j = 0; j < n; j++) {
        var v = series[i0 + j];
        if (v === null || v === undefined) { started = false; continue; }
        d += (started ? 'L' : 'M') + cx(j).toFixed(1) + ' ' + my(v).toFixed(1) + ' '; started = true;
      }
      if (!d) return;
      var p = svgEl('path', { d: d, fill: 'none', stroke: color, 'stroke-width': w, 'stroke-linejoin': 'round' });
      gM.appendChild(p);
      if (!reduced) {
        if (!gM.parentNode) svg.appendChild(gM);
        var L = 0; try { L = p.getTotalLength(); } catch (e3) { L = 0; }
        if (L) { p.style.setProperty('--len', L); p.setAttribute('stroke-dasharray', L); p.classList.add('draw'); p.style.animationDelay = delayMs + 'ms'; }
      }
    }
    macdPath(mac.line, 'var(--mmb-info)', 1.4, 880);
    macdPath(mac.signal, 'var(--mmb-warn)', 1.2, 960);
    gM.appendChild(paneLabel(mY0, 'MACD 12/26/9', 900));
    if (!gM.parentNode) svg.appendChild(gM);

    /* ── date axis: one label per month change ── */
    var gX = svgEl('g', { class: reduced ? '' : 'fade' });
    if (!reduced) gX.style.animationDelay = '780ms';
    var lastMon = '';
    for (k = 0; k < n; k++) {
      var mo = String(view[k].d).slice(0, 7);
      if (mo === lastMon) continue;
      lastMon = mo;
      if (cx(k) < X0 + 14 || cx(k) > X1 - 18) continue;
      var xt = svgEl('text', { x: cx(k), y: H - 6, fill: AXIS, 'font-size': 9.5, 'text-anchor': 'middle',
                               'font-family': 'ui-monospace,SFMono-Regular,Menlo,monospace' });
      xt.textContent = monLabel(view[k].d);
      gX.appendChild(xt);
    }
    svg.appendChild(gX);

    /* ── crosshair: the bar under the cursor, read out in the header ── */
    var gXh = svgEl('g', { class: 'mmb-cx-xh' });
    var vx = svgEl('line', { x1: 0, x2: 0, y1: pY0, y2: mY1, stroke: 'var(--mmb-muted)',
                             'stroke-width': 1, 'stroke-dasharray': '3 3' });
    var hy = svgEl('line', { x1: X0, x2: X1, y1: 0, y2: 0, stroke: 'var(--mmb-muted)',
                             'stroke-width': 1, 'stroke-dasharray': '3 3' });
    var dot = svgEl('circle', { r: 3, fill: 'var(--mmb-info)' });
    /* the two chips that make a crosshair feel like an instrument rather than a hairline:
       the price it is sitting on, in the axis gutter, and the date it is over, on the rail */
    var pxR = svgEl('rect', { x: X1 + 2, y: 0, width: PAD_R - 6, height: 15, rx: 4, fill: 'var(--mmb-panel2)' });
    var pxT = svgEl('text', { x: X1 + 5, y: 0, 'font-size': 9.5, 'font-weight': 700, fill: 'var(--mmb-text)',
                              'font-family': 'ui-monospace,SFMono-Regular,Menlo,monospace' });
    var dtR = svgEl('rect', { x: 0, y: H - 16, width: 52, height: 14, rx: 4, fill: 'var(--mmb-panel2)' });
    var dtT = svgEl('text', { x: 0, y: H - 5.6, 'font-size': 9, 'text-anchor': 'middle', fill: 'var(--mmb-text)',
                              'font-family': 'ui-monospace,SFMono-Regular,Menlo,monospace' });
    gXh.appendChild(vx); gXh.appendChild(hy); gXh.appendChild(dot);
    gXh.appendChild(pxR); gXh.appendChild(pxT); gXh.appendChild(dtR); gXh.appendChild(dtT);
    svg.appendChild(gXh);

    return { svg: svg, view: view, n: n, cx: cx, py: py, X0: X0, X1: X1, W: W, H: H,
             xh: { g: gXh, v: vx, h: hy, dot: dot, pxR: pxR, pxT: pxT, dtR: dtR, dtT: dtT },
             last: lastBar, prev: view[n - 2] || view[n - 1] };
  }

  /* ── mount: shell first (so the reply never waits on a fetch), then the live draw ── */
  function mountChart(host, j) {
    var ticker = String(j.ticker || '').toUpperCase().slice(0, 12);
    var tf = String(j.timeframe || 'DAILY').toLowerCase();
    var box = el('div', 'mmb-cx');
    var head = el('div', 'mmb-cx-h');
    var sym = el('span', 'mmb-cx-sym'); sym.textContent = ticker || '—';
    var tfc = el('span', 'mmb-cx-tf'); tfc.textContent = zh() ? (tf === 'daily' ? '日线' : tf) : tf;
    var sp = el('div', 'sp');
    var read = el('div', 'mmb-cx-read');
    head.appendChild(sym); head.appendChild(tfc); head.appendChild(sp); head.appendChild(read);
    box.appendChild(head);
    var body = el('div', 'mmb-cx-body');
    box.appendChild(body);
    host.appendChild(box);

    function fallback() {
      /* the server's picture, when we have no bars of our own for this symbol */
      if (!j.svg) {
        box.removeChild(body);
        var m = el('div', 'mmb-cx-miss');
        m.textContent = L('No daily bars for ' + ticker + ' — the read below stands on its own.',
                          ticker + ' 暂无日线数据 — 下方研判独立成立。');
        box.appendChild(m);
        return;
      }
      box.remove();
      var w = el('div', 'mmb-chart'); w.innerHTML = j.svg; host.appendChild(w); stickAfter();
    }

    fetchBars(ticker).then(function (bars) {
      if (!bars) { fallback(); return; }
      var built = null;
      function render() {
        body.textContent = '';
        built = drawChart(body, ticker, tf, bars);
        box.classList.toggle('narrow', built.W < 470);
        body.appendChild(built.svg);
        paintRead(null);
        wireCrosshair();
        stickAfter();
      }
      /* header readout: last close + day change at rest, the hovered bar while tracking */
      function paintRead(bar) {
        read.textContent = '';
        var b = bar || built.last, prev = bar ? null : built.prev;
        if (bar) {
          [[L('O', '开'), bar.o], [L('H', '高'), bar.h], [L('L', '低'), bar.l], [L('C', '收'), bar.c]]
            .forEach(function (pair) {
              var s = el('span'); var b2 = el('b'); b2.textContent = pair[0] + ' ';
              s.appendChild(b2); s.appendChild(DOC.createTextNode(fmtPrice(pair[1]))); read.appendChild(s);
            });
          var vsp = el('span', 'mmb-cx-vol'); var vb = el('b'); vb.textContent = L('V ', '量 ');
          vsp.appendChild(vb); vsp.appendChild(DOC.createTextNode(fmtVol(bar.v))); read.appendChild(vsp);
          var ch = bar.o ? (bar.c - bar.o) / bar.o * 100 : 0;
          var cs = el('span', 'mmb-cx-chg ' + (ch >= 0 ? 'up' : 'dn'));
          cs.textContent = (ch >= 0 ? '+' : '') + ch.toFixed(2) + '%';
          read.appendChild(cs);
          return;
        }
        var last = el('span', 'mmb-cx-last'); last.textContent = fmtPrice(b.c); read.appendChild(last);
        if (prev && prev.c) {
          var d = (b.c - prev.c) / prev.c * 100;
          var cg = el('span', 'mmb-cx-chg ' + (d >= 0 ? 'up' : 'dn'));
          cg.textContent = (d >= 0 ? '+' : '') + d.toFixed(2) + '%';
          read.appendChild(cg);
        }
      }
      function wireCrosshair() {
        var svg = built.svg;
        function track(ev) {
          var r = svg.getBoundingClientRect();
          var x = (ev.clientX - r.left) / r.width * built.W;
          var idx = Math.round((x - built.X0) / ((built.X1 - built.X0) / built.n) - 0.5);
          if (idx < 0) idx = 0; if (idx > built.n - 1) idx = built.n - 1;
          var bar = built.view[idx], px = built.cx(idx), pyv = built.py(bar.c);
          var xh = built.xh;
          xh.v.setAttribute('x1', px); xh.v.setAttribute('x2', px);
          xh.h.setAttribute('y1', pyv); xh.h.setAttribute('y2', pyv);
          xh.dot.setAttribute('cx', px); xh.dot.setAttribute('cy', pyv);
          xh.pxR.setAttribute('y', pyv - 7.5); xh.pxT.setAttribute('y', pyv + 3.4);
          xh.pxT.textContent = fmtPrice(bar.c);
          var dx = Math.max(built.X0, Math.min(built.X1 - 52, px - 26));
          xh.dtR.setAttribute('x', dx); xh.dtT.setAttribute('x', dx + 26);
          xh.dtT.textContent = String(bar.d).slice(5);
          box.classList.add('live');
          paintRead(bar);
        }
        function leave() { box.classList.remove('live'); paintRead(null); }
        svg.addEventListener('pointermove', track);
        svg.addEventListener('pointerdown', track);
        svg.addEventListener('pointerleave', leave);
      }
      render();

      var foot = el('div', 'mmb-cx-foot');
      [[L('EMA 20', 'EMA 20'), 'var(--mmb-info)'], [L('SMA 50', 'SMA 50'), 'var(--mmb-violet)']]
        .forEach(function (kv) {
          var s = el('span', 'mmb-cx-key'); s.style.color = kv[1];
          var i2 = DOC.createElement('i'); s.appendChild(i2);
          var tx = el('span'); tx.style.color = 'var(--mmb-muted)'; tx.textContent = kv[0];
          s.appendChild(tx); foot.appendChild(s);
        });
      foot.appendChild(el('div', 'sp'));
      var src = el('span', 'mmb-cx-src');
      src.textContent = built.view[built.n - 1].d + ' · ' + built.n + (zh() ? ' 根K线' : ' bars');
      foot.appendChild(src);
      box.appendChild(foot);

      /* a resize or a theme/language flip is a re-render, never a stretched picture */
      var rt = 0;
      function relayout() { if (rt) clearTimeout(rt); rt = setTimeout(function () { if (box.isConnected) render(); }, 120); }
      if (typeof ResizeObserver === 'function') {
        var ro = new ResizeObserver(relayout);
        ro.observe(box);
      }
      DOC.addEventListener('themechange', relayout);
      DOC.addEventListener('langchange', relayout);
    });
  }

  /* ── gateway auth: attach the Supabase Bearer token (gateway ignores the cookie) ── */
  function withAuth(h) {
    h = h || {};
    if (!(window.MDXAuth && window.MDXAuth.client)) return Promise.resolve(h);
    return window.MDXAuth.client().then(function (sb) { return sb.auth.getSession(); })
      .then(function (r) { var t = r && r.data && r.data.session && r.data.session.access_token; if (t) h['Authorization'] = 'Bearer ' + t; return h; })
      .catch(function () { return h; });
  }

  /* ── quota / me ── */
  /* Always called on boot, even signed-out: /api/brain/me returns tier 'guest' (200) when the
     operator has enabled free guest access, or 401 when it is off. A 'guest' tier flips the
     widget into guest mode (chat UI, not the sign-in gate); a 401 leaves the gate up. */
  function loadQuotas() {
    withAuth().then(function (h) { return fetch(API + '/api/brain/me', { headers: h, credentials: 'include' }); })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d) { if (!authed) enterGuest(false); return; }
        quotas = d.quotas || {};
        /* Signed-out + tier 'guest' → guest mode ON; signed-out + anything else → gate. */
        if (!authed) enterGuest(d.tier === 'guest');
        /* limit < 0 = unlimited (operator allowlist) → Pro eligible; limit 0 = lane locked. */
        proEligible = !!(quotas.pro && quotas.pro.limit !== 0);
        researchBtn.classList.toggle('mmb-off', !proEligible);
        restorePrefs();   /* re-apply the remembered lane (or clear it if Pro just lapsed) */
        renderQuota();
      }).catch(function () { if (!authed) enterGuest(false); });
  }
  function renderQuota() {
    var q = quotas[researchMode ? 'pro' : lane];
    if (!q) { qEl.textContent = ''; qEl.removeAttribute('title'); return; }
    /* the mark, not a glyph: the meter and the lane control now say "Pro" the same way,
       so "which bucket is this spending" is answered without reading a word. */
    var pre = laneMark((researchMode || lane === 'pro') ? 'pro' : 'fast');
    function meter(txt) { qEl.innerHTML = pre + '<span>' + esc(txt) + '</span>'; }
    /* title is English-only per house law (no translated text in title= attrs). */
    if (q.limit < 0) { meter('\u221e'); qEl.className = 'mmb-q'; qEl.setAttribute('title', 'Unlimited'); return; }  /* unlimited */
    meter(q.remaining + '/' + q.limit);
    qEl.setAttribute('title', q.period === 'day' ? (q.remaining + ' of ' + q.limit + ' free messages left today') : (q.remaining + ' of ' + q.limit + ' left'));
    qEl.className = 'mmb-q' + (q.remaining <= 0 ? ' empty' : (q.remaining <= Math.max(1, q.limit * 0.15) ? ' warn' : ''));
  }

  /* ── threads ── */
  function loadThreads() {
    withAuth().then(function (h) { return fetch(API + '/api/brain/threads', { headers: h, credentials: 'include' }); })
      .then(function (r) { return r.ok ? r.json() : { threads: [] }; })
      .then(function (d) { renderThreads((d && d.threads) || []); }).catch(function () {});
  }
  var allThreads = [];
  var PENCIL = '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>';
  var TRASH = '<path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M6 6l1 14a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-14"/>';
  function buildThreadItem(t) {
    var d = el('div', 'mmb-ti' + (t.id === threadId ? ' on' : '')); d.dataset.id = t.id;
    var date = ''; try { date = new Date(t.updated_at).toLocaleDateString(); } catch (e) {}
    var body = el('div', 'mmb-ti-body');
    var tt = el('div', 'tt'); tt.textContent = t.title || L('Untitled', '未命名');
    var tm = el('div', 'tm'); tm.textContent = (t.lane || 'fast') + ' · ' + date;
    body.appendChild(tt); body.appendChild(tm);
    /* row-open (guarded so action clicks don't also open the thread) */
    body.addEventListener('click', function () { openThread(t.id); if (!panel.classList.contains('max')) panel.classList.remove('show-side'); });
    d.appendChild(body);

    var acts = el('div', 'mmb-ti-acts');
    var ren = el('button', 'mmb-ti-act'); ren.type = 'button'; ren.title = 'Rename'; ren.setAttribute('aria-label', L('Rename chat', '重命名对话')); ren.innerHTML = ic(PENCIL);
    ren.addEventListener('click', function (e) { e.stopPropagation(); startRename(d, t, tt); });
    var del = el('button', 'mmb-ti-act'); del.type = 'button'; del.title = 'Delete'; del.setAttribute('aria-label', L('Delete chat', '删除对话')); del.innerHTML = ic(TRASH);
    del.addEventListener('click', function (e) { e.stopPropagation(); enterDelete(d, t); });
    acts.appendChild(ren); acts.appendChild(del); d.appendChild(acts);

    /* confirm-delete overlay (hidden until armed) */
    var confirm = el('div', 'mmb-ti-confirm');
    var q = el('span', 'mmb-ti-q'); q.textContent = L('Delete?', '删除？'); confirm.appendChild(q);
    var yes = el('button', 'mmb-ti-yes'); yes.type = 'button'; yes.title = 'Confirm delete'; yes.setAttribute('aria-label', L('Confirm delete', '确认删除')); yes.innerHTML = ic('<path d="M5 12.5l4 4 10-10"/>');
    var no = el('button', 'mmb-ti-no'); no.type = 'button'; no.title = 'Cancel'; no.setAttribute('aria-label', L('Cancel', '取消')); no.innerHTML = ic('<path d="M6 6l12 12M18 6L6 18"/>');
    yes.addEventListener('click', function (e) { e.stopPropagation(); doDelete(d, t); });
    no.addEventListener('click', function (e) { e.stopPropagation(); leaveDelete(d); });
    confirm.appendChild(yes); confirm.appendChild(no); d.appendChild(confirm);
    return d;
  }
  /* ── rename: swap title for an inline input (Enter=save, Esc=cancel, blur=save-if-changed) ── */
  function startRename(row, t, tt) {
    if (row.querySelector('.mmb-ti-input')) return;
    var inp = el('input', 'mmb-ti-input'); inp.type = 'text'; inp.maxLength = 80; inp.value = t.title || '';
    var orig = t.title || '';
    tt.style.display = 'none'; tt.parentNode.insertBefore(inp, tt);
    var done = false;
    function save(commit) {
      if (done) return; done = true;
      var v = inp.value.trim().slice(0, 80);
      inp.remove(); tt.style.display = '';
      if (commit && v && v !== orig) { tt.textContent = v; t.title = v; patchThread(t.id, v, orig, tt); }
    }
    inp.addEventListener('keydown', function (e) {
      e.stopPropagation();
      if (e.key === 'Enter') { e.preventDefault(); save(true); }
      else if (e.key === 'Escape') { e.preventDefault(); save(false); }
    });
    inp.addEventListener('click', function (e) { e.stopPropagation(); });
    inp.addEventListener('blur', function () { save(true); });
    setTimeout(function () { inp.focus(); inp.select(); }, 0);
  }
  function patchThread(id, title, orig, tt) {
    withAuth({ 'Content-Type': 'application/json' })
      .then(function (h) { return fetch(API + '/api/brain/threads/' + id, { method: 'PATCH', headers: h, credentials: 'include', body: JSON.stringify({ title: title }) }); })
      .then(function (r) { if (!r.ok) throw 0; })
      .catch(function () { /* revert on 401/404/error */ if (tt) tt.textContent = orig || L('Untitled', '未命名'); var th = findThread(id); if (th) th.title = orig; loadThreads(); });
  }
  /* ── delete: row enters a confirm state (auto-reverts after 4s) ── */
  function enterDelete(row, t) {
    root.querySelectorAll('.mmb-ti.confirming').forEach(function (r) { if (r !== row) leaveDelete(r); });
    row.classList.add('confirming');
    if (row._delTimer) clearTimeout(row._delTimer);
    row._delTimer = setTimeout(function () { leaveDelete(row); }, 4000);
  }
  function leaveDelete(row) { row.classList.remove('confirming'); if (row._delTimer) { clearTimeout(row._delTimer); row._delTimer = 0; } }
  function doDelete(row, t) {
    if (row._delTimer) { clearTimeout(row._delTimer); row._delTimer = 0; }
    var id = t.id;
    row.style.display = 'none';                              /* optimistic remove */
    allThreads = allThreads.filter(function (x) { return x.id !== id; });
    if (id === threadId) newChat();
    withAuth().then(function (h) { return fetch(API + '/api/brain/threads/' + id, { method: 'DELETE', headers: h, credentials: 'include' }); })
      .then(function (r) { if (!r.ok) throw 0; })
      .catch(function () { loadThreads(); });                /* 401/404/error → reload truth */
  }
  function findThread(id) { for (var i = 0; i < allThreads.length; i++) if (allThreads[i].id === id) return allThreads[i]; return null; }
  function paintThreads() {
    if (guestMode) { paintGuestThreads(); return; }   /* guests see the sign-in prompt, not the (empty) list */
    if (!allThreads.length) { tlist.innerHTML = '<div class="mmb-th-empty">' + L('Your conversations appear here.', '你的对话会显示在这里。') + '</div>'; return; }
    var q = ((searchIn && searchIn.value) || '').trim().toLowerCase();
    var items = q ? allThreads.filter(function (t) { return (t.title || '').toLowerCase().indexOf(q) !== -1; }) : allThreads;
    if (!items.length) { tlist.innerHTML = '<div class="mmb-th-empty">' + L('No chats match your search.', '没有匹配的对话。') + '</div>'; return; }
    tlist.innerHTML = '';
    items.forEach(function (t) { tlist.appendChild(buildThreadItem(t)); });
  }
  function renderThreads(threads) { allThreads = threads || []; paintThreads(); }
  function toggleSearch(force) {
    if (!searchWrap) return;
    var open = typeof force === 'boolean' ? force : !searchWrap.classList.contains('on');
    searchWrap.classList.toggle('on', open);
    if (open) { setTimeout(function () { searchIn && searchIn.focus(); }, 0); }
    else if (searchIn) { searchIn.value = ''; paintThreads(); }
  }
  /* openThread(id, done): `done` fires once the messages are painted — the resume path
     needs it so it can attach a still-running turn to the thread it belongs to. */
  function openThread(id, done) {
    abortStream();   /* switching threads mid-stream must tear the old stream down first */
    threadId = id;
    root.querySelectorAll('.mmb-ti').forEach(function (el) { el.classList.toggle('on', el.dataset.id === id); });
    withAuth().then(function (h) { return fetch(API + '/api/brain/threads/' + id, { headers: h, credentials: 'include' }); })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d) return;
        clearMsgs(); scroll.textContent = '';
        var lastDay = '';
        (d.messages || []).forEach(function (m) {
          var ms = 0; try { ms = m.created_at ? new Date(m.created_at).getTime() : 0; } catch (e) {}
          if (ms) { var dk = new Date(ms).toDateString(); if (dk !== lastDay) { addDaySep(ms); lastDay = dk; } }
          appendMsg(m.role, m.content, ms || undefined);
        });
        markLastAssistant(); pinned = true; scroll.scrollTop = scroll.scrollHeight;
        ta.value = ''; autosize(); syncSend(); updateCounter(); restoreDraft();
        if (done) { try { done(d.messages || []); } catch (e) {} }
      }).catch(function () {});
  }

  /* ── messages ── */
  function clearMsgs() { scroll.textContent = ''; renderEmpty(); pinned = true; hideJump(); }
  /* Relative timestamp (11px muted). now/2m/1h/Yesterday/date. */
  function relTime(ms) {
    var d = ms ? new Date(ms) : new Date(), now = Date.now(), diff = Math.floor((now - d.getTime()) / 1000);
    if (isNaN(diff)) return '';
    if (diff < 45) return L('just now', '刚刚');
    if (diff < 3600) return (Math.max(1, Math.round(diff / 60))) + L('m', ' 分钟前');
    if (diff < 86400) return (Math.round(diff / 3600)) + L('h', ' 小时前');
    var y = new Date(now); y.setDate(y.getDate() - 1);
    if (d.toDateString() === y.toDateString()) return L('Yesterday', '昨天');
    try { return d.toLocaleDateString(zh() ? 'zh-CN' : 'en-US', { month: 'short', day: 'numeric' }); } catch (e) { return d.toLocaleDateString(); }
  }
  function dayLabel(ms) {
    var d = new Date(ms), now = new Date();
    if (d.toDateString() === now.toDateString()) return L('Today', '今天');
    var y = new Date(); y.setDate(y.getDate() - 1);
    if (d.toDateString() === y.toDateString()) return L('Yesterday', '昨天');
    try { return d.toLocaleDateString(zh() ? 'zh-CN' : 'en-US', { year: 'numeric', month: 'short', day: 'numeric' }); } catch (e) { return d.toLocaleDateString(); }
  }
  function addDaySep(ms) {
    var sep = el('div', 'mmb-daysep'); var s = el('span'); s.textContent = dayLabel(ms); sep.appendChild(s); scroll.appendChild(sep);
  }
  /* Build the assistant action row: copy · regenerate (last only) · timestamp.
     Space is always reserved (opacity reveal on hover) so nothing shifts. */
  function buildActions(bub, ts) {
    var row = el('div', 'mmb-actions');
    var copy = el('button', 'mmb-abtn mmb-copy'); copy.type = 'button'; copy.title = 'Copy'; copy.setAttribute('aria-label', L('Copy answer', '复制回答')); copy.innerHTML = CLIP;
    copy.addEventListener('click', function (e) {
      e.stopPropagation();
      var payload = String(bub._raw != null ? bub._raw : ((bub.querySelector('.mmb-txt') || bub).innerText || '')).trim();
      try {
        if (!(navigator.clipboard && navigator.clipboard.writeText)) return;
        navigator.clipboard.writeText(payload).then(function () { copy.innerHTML = CHECK; setTimeout(function () { copy.innerHTML = CLIP; }, 1200); }).catch(function () {});
      } catch (e2) {}
    });
    row.appendChild(copy);
    var regen = el('button', 'mmb-abtn mmb-regen'); regen.type = 'button'; regen.title = 'Regenerate'; regen.setAttribute('aria-label', L('Regenerate reply', '重新生成'));
    regen.innerHTML = ic('<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>');
    regen.addEventListener('click', function (e) { e.stopPropagation(); regenerate(); });
    row.appendChild(regen);
    var time = el('span', 'mmb-time'); time._ts = ts || Date.now(); time.textContent = relTime(time._ts);
    row.appendChild(time);
    return row;
  }
  /* Only the LAST assistant message shows its regenerate button (client resend of the
     last user turn). Called whenever messages change. */
  function markLastAssistant() {
    var msgs = scroll.querySelectorAll('.mmb-msg.assistant');
    for (var i = 0; i < msgs.length; i++) msgs[i].classList.toggle('mmb-last', i === msgs.length - 1);
  }
  function appendMsg(role, content, ts) {
    var es = $('#mmb-emptystate'); if (es) es.remove();
    var d = el('div', 'mmb-msg ' + role);
    var b = el('div', 'mmb-bub');
    if (role === 'user') {
      var p = el('p'); p.textContent = content == null ? '' : String(content); b.appendChild(p);
    } else {
      /* assistant: ghost block, orb glyph, charts sibling kept separate from the text
         node so a delta re-render never wipes an inline chart. */
      var orb = el('span', 'mmb-orbmark'); orb.innerHTML = '<svg viewBox="0 0 24 24"><path d="' + ORB_PATH + '"/></svg>'; b.appendChild(orb);
      var charts = el('div', 'mmb-charts'); b.appendChild(charts);
      var txt = el('div', 'mmb-txt'); if (content) renderMdInto(txt, content); b.appendChild(txt);
      b._raw = content || '';
      b.appendChild(buildActions(b, ts));
    }
    d.appendChild(b); scroll.appendChild(d);
    if (role === 'assistant') markLastAssistant();
    stick(); return b;
  }
  function bubTxt(b) { return b.querySelector('.mmb-txt') || b; }

  /* ── scroll pinning + jump pill ──────────────────────────────────────────────
     "pinned" = user is riding the bottom (within 90px). Scrolling up unpins; when
     unpinned and new content lands, a "↓ Latest" pill fades in above the composer. */
  var pinned = true, jumpPill = null;
  function atBottom() { return (scroll.scrollHeight - scroll.scrollTop - scroll.clientHeight) < 90; }
  function stick() { if (pinned) scroll.scrollTop = scroll.scrollHeight; }
  function stickAfter() { if (pinned) scroll.scrollTop = scroll.scrollHeight; else showJump(); }
  function toBottom() { pinned = true; scroll.scrollTop = scroll.scrollHeight; hideJump(); }
  function showJump() {
    if (!jumpPill) {
      jumpPill = el('button', 'mmb-jump'); jumpPill.type = 'button';
      jumpPill.innerHTML = '<svg viewBox="0 0 24 24"><path d="M12 5v14M6 13l6 6 6-6"/></svg>';
      var lbl = el('span', 'mmb-l'); lbl.setAttribute('data-en', 'Latest'); lbl.setAttribute('data-zh', '最新'); lbl.textContent = L('Latest', '最新'); jumpPill.appendChild(lbl);
      jumpPill.setAttribute('aria-label', L('Jump to latest', '跳到最新'));
      jumpPill.addEventListener('click', toBottom);
      /* anchored to the composer wrapper so it sits just above the input, not off the top */
      root.querySelector('.mmb-comp').appendChild(jumpPill);
    }
    jumpPill.classList.add('on');
  }
  function hideJump() { if (jumpPill) jumpPill.classList.remove('on'); }

  /* [icon-paths, EN, ZH] — kept dual-language so the chips re-localize on a live
     language switch (the array is built once at load; text is picked at render). */
  var PROMPTS = [
    ['M3 3v18h18|M7 14l4-4 3 3 5-6', 'What regime are we in and what’s driving it?', '现在是什么市场周期？由什么驱动？'],
    ['M4 20V10M10 20V4M16 20v-7M22 20H2', 'Which themes have the strongest momentum?', '哪些主题动量最强？'],
    ['M12 3a9 9 0 1 0 9 9|M12 7v5l3 2', 'What should I be watching this week?', '这周该关注什么？'],
    ['M4 5h16M4 12h16M4 19h10', 'How is my watchlist doing?', '我的自选股表现如何？']
  ];
  function renderEmpty() {
    var name = '';
    try { var u = window.MDXAuth && window.MDXAuth.user && window.MDXAuth.user(); if (u) { name = (u.user_metadata && (u.user_metadata.display_name || u.user_metadata.name)) || (u.email ? u.email.split('@')[0] : ''); } } catch (e) {}
    name = name ? (name.charAt(0).toUpperCase() + name.slice(1)) : '';
    var cards = PROMPTS.map(function (p, i) {
      var paths = p[0].split('|').map(function (d) { return '<path d="' + d + '"/>'; }).join('');
      var txt = L(p[1], p[2]);
      return '<button class="mmb-cardp" style="--i:' + i + '" data-p="' + esc(txt) + '"><div class="ci"><svg viewBox="0 0 24 24">' + paths + '</svg></div><span class="cp">' + esc(txt) + '</span></button>';
    }).join('');
    var hero = '<div class="mmb-empty" id="mmb-emptystate"><div class="mmb-hero"><h1>' +
      (name ? '<span class="g1">' + L('Hi there, ', '你好，') + '</span><span class="nm">' + esc(name) + '</span><br>' : '') +
      '<span class="g2">' + L('What do you want to know?', '你想了解什么？') + '</span></h1>' +
      '<p>' + L('Your desk copilot — it reads the live signals, regimes and flow on this dashboard and the Terminal, and explains what they mean.', '你的桌面副驾 — 读取本看板与终端的实时信号、周期与资金流，并解释其含义。') + '</p></div>' +
      '<div class="mmb-cards">' + cards + '</div></div>';
    scroll.innerHTML = hero;
  }

  /* re-localize the chrome in place when the host switches language. Both hosts
     set <html data-lang> (so zh() is already correct); we just repaint: dual-lang
     LB() spans + data-ph placeholders flip, and the state-dependent renderers that
     bake strings via L() are re-run (empty-state hero/chips, thread list). Already-
     sent messages keep their original language — they're content, not chrome. */
  function relabel() {
    root.querySelectorAll('.mmb-l[data-en]').forEach(function (el) { el.textContent = zh() ? el.getAttribute('data-zh') : el.getAttribute('data-en'); });
    root.querySelectorAll('[data-ph-en]').forEach(function (el) { el.placeholder = zh() ? el.getAttribute('data-ph-zh') : el.getAttribute('data-ph-en'); });
    paintPlaceholder();   /* an armed research pass keeps its own prompt through the switch */
    if (launch) launch.setAttribute('aria-label', zh() ? '问操盘大脑' : 'Ask Mastermind');  /* orb-only on phones: keep its accessible name in sync */
    researchBtn.setAttribute('aria-label', L('Deep Research', '深度研究'));   /* label shortens to the mark on phones */
    if ($('#mmb-emptystate')) renderEmpty();
    paintThreads();   /* self-routes to the guest sign-in prompt when in guest mode */
    renderQuota();     /* refresh the meter's title in the new language sense */
    setBusy(streaming);   /* send↔stop label carries the shortcut — re-say it in the new language */
  }

  /* ── send (SSE) ──────────────────────────────────────────────────────────────
     send() builds a payload from the live composer + attaches the user bubble, then
     hands off to runStream(). runStream() is payload-only so Regenerate and Retry can
     replay the exact same turn (text + images + lane + thread) with no backend change. */
  var lastTurn = null;   // { text, imgs, lane, mode } — last user turn, for regenerate
  var priorTurn = null;  // the one before it — a retract rolls `lastTurn` back to this
  function send(text) {
    text = (text || ta.value).trim();
    var imgs = pendingImages.slice();
    if ((!text && !imgs.length) || streaming) return;
    /* The active chart/ticker can change long after the widget booted. Resolve it
       at the moment of every send so Terminal and dashboard never keep a stale
       launch-time chip (the NVDA → 600036.SS incident). */
    refreshCtx();
    /* Guests may send (Fast lane) without the sign-in modal; only fully-gated (non-guest,
       signed-out) sessions are bounced to sign-in. */
    if (!authed && !guestMode && window.MDXAuth && window.MDXAuth.enabled && window.MDXAuth.enabled()) { window.MDXAuth.open('signin'); return; }
    /* lang travels with every turn: the server pins the reply AND the follow-up chips to
       it, so a Chinese thread history can never drag an English turn's buttons into
       Chinese. A message typed in the other language still wins (server-side). */
    var ctx = { page: (ANCHOR === 'top' ? 'terminal' : 'dashboard'), lang: (zh() ? 'zh' : 'en') }; if (ctxSymbol) ctx.symbol = ctxSymbol;
    /* an "explain this panel" request carries the panel key once, then clears */
    if (explainPanel) { ctx.panel = explainPanel; explainPanel = null; }
    var payload = { text: text, imgs: imgs, lane: researchMode ? 'pro' : lane, mode: researchMode ? 'research' : 'chat', ctx: ctx };
    priorTurn = lastTurn;   /* retracting this turn must not leave Regenerate replaying it */
    lastTurn = { text: text, imgs: imgs, lane: payload.lane, mode: payload.mode };
    pendingImages = []; renderThumbs();
    ta.value = ''; autosize(); clearDraft(); syncSend(); updateCounter(); closeSlash();
    /* the composer answers the keystroke: one settle, retriggerable on a fast second send */
    boxEl.classList.remove('mmb-sent'); void boxEl.offsetWidth; boxEl.classList.add('mmb-sent');
    pinned = true; hideJump();
    runStream(payload, true);
  }
  /* Replay the last user turn on the same thread/lane (client resend, no backend change). */
  function regenerate() {
    if (streaming || !lastTurn) return;
    refreshCtx();
    runStream({ text: lastTurn.text, imgs: (lastTurn.imgs || []).slice(), lane: lastTurn.lane, mode: lastTurn.mode,
                ctx: (function () { var c = { page: (ANCHOR === 'top' ? 'terminal' : 'dashboard'), lang: (zh() ? 'zh' : 'en') }; if (ctxSymbol) c.symbol = ctxSymbol; return c; })() }, false);
  }
  /* ── durable turns ───────────────────────────────────────────────────────────
     A turn is owned by the SERVER (app/brain_runs.py), not by the socket that
     started it: POST /api/brain/stream answers with a `run` event carrying a run_id,
     and the brain keeps generating — and keeps persisting to the thread — whether or
     not this browser is still listening. So a dropped connection is no longer a lost
     reply, it is a reconnect: GET /api/brain/runs/{id}/stream?cursor=N replays the
     events we missed and follows the rest live.

     `cursor` counts the brain events we have consumed. The `run` envelope is never
     buffered server-side, so it is the one event that must NOT advance the cursor —
     otherwise every resume would skip a real event.

     Three recovery paths, tried in order:
       1. re-attach to the run buffer (exact replay, works for guests too);
       2. re-read the thread tail (survives an API restart / a run past its TTL);
       3. only then the "didn't make it through" card, with Retry. */
  var RUN_KEY = 'mm.brain.run';
  var RUN_MAX_AGE_MS = 25 * 60 * 1000;   /* under the server's 30-min run TTL */
  var RESUME_TRIES = 6;
  var PARK_FALLBACK_MS = 20000;          /* re-check even if visibilitychange never fires */
  var PARK_MAX = 6;                      /* then shelve — the tab is away, not broken */

  /* sessionStorage, NOT localStorage: the record belongs to ONE TAB. It has to survive
     a reload (the whole point), but it must not be shared — two tabs chatting at once
     would overwrite each other's run and a reload would drop tab A into tab B's
     conversation, or tab A's clearRun() would destroy tab B's only way back. */
  var runStore = (function () {
    try { var s = window.sessionStorage; s.setItem('mm.t', '1'); s.removeItem('mm.t'); return s; }
    catch (e) { return null; }
  })();
  function saveRun(T) {
    /* A finished/stopped turn must never re-arm itself: the cursor bump that follows
       the `done` event would otherwise rewrite the record clearRun() just deleted, and
       the next page load would try to resume a turn that is already on screen. */
    if (!T.runId || T.doneSeen || T.stopped || !runStore) return;
    try {
      runStore.setItem(RUN_KEY, JSON.stringify({
        id: T.runId, cursor: T.cursor, thread: T.threadId || threadId || null,
        q: (T.payload && T.payload.text) || '', ts: Date.now()
      }));
    } catch (e) {}
  }
  function loadRun() { try { return JSON.parse((runStore && runStore.getItem(RUN_KEY)) || 'null'); } catch (e) { return null; } }
  function clearRun() { try { if (runStore) runStore.removeItem(RUN_KEY); } catch (e) {} }

  /* Per-turn UI + parse state. Shared by the opening POST and by every later
     re-attachment, so a resumed stream paints into the same bubble it started in. */
  /* ── the reasoning ledger (think*) ────────────────────────────────────────────
     The gateway holds the whole answer back until it clears the advice filter, so the
     wait is the only thing the user has: this strip narrates it the way a colleague
     would. It reads DOWNWARD like a worksheet — finished steps above, the line that is
     running at the bottom, then the answer directly beneath it — so the eye travels
     through the work and into the reply instead of jumping back over it.

     Three things carry the narration, and none of them is a new string from the server:
       · the server's own bilingual label is the headline (leak law — every visible
         label ships from the gateway's two whitelists, never a tool name);
       · a family GLYPH picked from the tool name, so "read twenty things" is legible
         at a glance as price / flow / notes / chart work rather than twenty lines;
       · one plain clause under the live label (PHASE_SUB) saying what this stage is
         FOR — the part users kept asking for, and the part a label alone can't say.

     All state lives in ONE plain holder (`tl`) created by thinkInit(); every function
     below takes that holder and is a no-op once it has been torn down, so the send flow
     owns nothing but the holder itself and never has to guard a call. */
  function thinkInit(host, mode) {
    var tl = { node: el('div', 'mmb-think'), t0: Date.now(), key: '', label: '', detail: '', dcls: 'rd',
               ico: PHASE_IC.start, shown: [], record: [], checks: 0, timer: 0, dead: false };
    tl.rows = el('div', 'mmb-tk-rows'); tl.node.appendChild(tl.rows);
    /* Deep Research states itself once, as a standing first line (never rotated out). */
    if (mode === 'research') {
      var seed = thinkRow({ t: L('Deep research — a fuller pass', '深度研究 — 更完整的一遍'), i: MARK_RESEARCH });
      seed.classList.add('mode'); tl.rows.appendChild(seed);
      tl.record.push({ t: L('Deep research — a fuller pass', '深度研究 — 更完整的一遍'), i: MARK_RESEARCH });
    }
    var head = el('div', 'mmb-tk-h');
    tl.icoEl = el('span', 'mmb-tk-ic'); tl.icoEl.innerHTML = ic(tl.ico);
    var body = el('div', 'mmb-tk-body');
    tl.lab = el('span', 'lb'); tl.lab.textContent = L('Reading your question', '正在理解您的问题');
    tl.sub = el('span', 'sb'); tl.sub.textContent = L(PHASE_SUB.start[0], PHASE_SUB.start[1]);
    tl.chip = el('span', 'rd'); tl.chip.style.display = 'none';
    tl.clock = el('span', 'mmb-tk-t'); tl.clock.textContent = '0:00';
    tl.label = tl.lab.textContent; tl.key = tl.label + '|';
    var lbrow = el('div', 'lbrow'); lbrow.appendChild(tl.lab); lbrow.appendChild(tl.chip);
    body.appendChild(lbrow); body.appendChild(tl.sub);
    head.appendChild(tl.icoEl); head.appendChild(body); head.appendChild(tl.clock);
    tl.node.appendChild(head);
    tl.timer = setInterval(function () {
      var s = Math.max(0, Math.floor((Date.now() - tl.t0) / 1000));
      tl.clock.textContent = Math.floor(s / 60) + ':' + ('0' + (s % 60)).slice(-2);
    }, 1000);
    if (host) host.appendChild(tl.node);
    return tl;
  }
  /* One ledger line: glyph node on the spine, the label, and the qualifier as a data chip
     (a ticker in mono blue, a size estimate in plain mono). Shared by the live strip and
     by the receipt's unfolded record, so a step reads identically in both places. */
  function thinkRow(r) {
    var row = el('div', 'mmb-tk-row');
    var i = el('span', 'mmb-tk-ic'); i.innerHTML = ic(r.i || FAM.data);
    var t = el('span', 'rl'); t.textContent = r.t;
    row.appendChild(i); row.appendChild(t);
    if (r.d) { var d = el('span', r.dc || 'rd'); d.textContent = r.d; row.appendChild(d); }
    return row;
  }
  /* the strip follows the reply: placeholder bubble → real bubble, above the text */
  function thinkMount(tl, bub) { if (!tl || tl.dead) return; bub.insertBefore(tl.node, bubTxt(bub)); }
  /* Retire the live line. Kept in the record forever, on screen only while it is recent —
     a four-line window is what fits the compact panel without pushing the composer. */
  function thinkRetire(tl) {
    if (!tl.label) return;
    var r = { t: tl.label, d: tl.detail, dc: tl.dcls, i: tl.ico };
    tl.record.push(r);
    var row = thinkRow(r); tl.rows.appendChild(row); tl.shown.push(row);
    while (tl.shown.length > 4) { var old = tl.shown.shift(); if (old.parentNode) old.remove(); }
  }
  /* Move to a step. `o.label` is the headline, `o.detail` the qualifier (a symbol, or the
     writing size estimate), `o.ico` the glyph. Re-marking the SAME step only repaints the
     head — that is how the writing estimate grows without spamming the list. Tool steps
     key on their detail too (same tool, new symbol = a new step) and count toward the
     check tally. */
  function thinkStep(tl, o) {
    if (!tl || tl.dead || !o.label) return;
    var key = o.label + '|' + (o.isTool ? (o.detail || '') : '');
    if (key !== tl.key) {
      thinkRetire(tl); tl.key = key;
      /* re-trigger the label crossfade: a phase change lands as a move, not a flicker */
      tl.lab.classList.remove('mmb-swap'); void tl.lab.offsetWidth; tl.lab.classList.add('mmb-swap');
    }
    /* the chip's "N checks" counts tool EVENTS (work done), not rendered lines — two
       same-labelled reads in one round are still two checks (review MINOR-5) */
    if (o.isTool) tl.checks++;
    /* a finished tool line keeps its symbol (that is a fact worth reading back); a stage
       line drops its size estimate, which is progress, not a result. */
    tl.label = o.label;
    tl.detail = o.isTool ? (o.detail || '') : '';
    tl.dcls = 'rd';
    tl.ico = o.ico || FAM.data;
    tl.lab.textContent = o.label;
    tl.sub.textContent = o.sub || '';
    tl.icoEl.innerHTML = ic(tl.ico);
    if (o.detail) { tl.chip.textContent = o.detail; tl.chip.className = o.dcls || 'rd'; tl.chip.style.display = ''; }
    else { tl.chip.style.display = 'none'; }
    stickAfter();
  }
  /* one `status` event. `beat` is the keepalive heartbeat — liveness only, no visual
     change (the clock is client-side and never stalls). */
  function thinkStatus(tl, j) {
    if (!tl || tl.dead) return;
    /* a re-attached turn starts a fresh client clock, but the wire already knows the
       real age — floor t0 with the server's elapsed_ms so the clock and the final
       receipt never under-report a resumed run (review MINOR-6) */
    if (j.elapsed_ms > 0) { var t0s = Date.now() - j.elapsed_ms; if (t0s < tl.t0) tl.t0 = t0s; }
    if (j.phase === 'beat') return;
    var writing = j.phase === 'writing' && j.n > 0;
    var sub = PHASE_SUB[j.phase];
    if (j.phase === 'model') sub = MODEL_SUB[Math.min(MODEL_SUB.length - 1, Math.max(0, (j.n || 1) - 1))];
    thinkStep(tl, {
      label: evLabel(j, '', ''),
      detail: writing ? ('~' + (zh() ? (j.n + ' 字') : (Math.max(1, Math.round(j.n / 6)) + ' words'))) : evDetail(j),
      dcls: writing ? 'rn' : 'rd',
      sub: sub ? L(sub[0], sub[1]) : '',
      ico: PHASE_IC[j.phase] || PHASE_IC.model
    });
  }
  /* one `tool` event — an old gateway sends no labels, so fall back to the house line */
  function thinkTool(tl, j) {
    var key = toolFam(j.name), fam = FAM_SUB[key] || FAM_SUB.data;
    thinkStep(tl, {
      label: evLabel(j, 'Reading market data', '读取市场数据'),
      detail: evDetail(j), isTool: true,
      sub: L(fam[0], fam[1]),
      ico: FAM[key] || FAM.data
    });
  }
  /* Fold into the receipt chip above the finished answer, then tear the strip down. */
  function thinkCollapse(tl, bub) {
    if (!tl || tl.dead) return null;
    thinkRetire(tl); tl.label = '';
    var secs = Math.max(0, Math.round((Date.now() - tl.t0) / 1000)), record = tl.record;
    thinkTeardown(tl);
    var wrap = el('div', 'mmb-recap');
    var btn = el('button', 'mmb-chip'); btn.type = 'button'; btn.setAttribute('aria-expanded', 'false');
    btn.insertAdjacentHTML('afterbegin',
      '<svg class="ck" viewBox="0 0 24 24" aria-hidden="true"><path d="M4.5 6.5h11M4.5 11h11M4.5 15.5h6.5"/><path d="M15.5 15l2.4 2.4 4-4.4"/></svg>');
    var line = el('span');
    line.textContent = tl.checks
      ? L('Analyzed for ' + secs + 's · ' + tl.checks + (tl.checks === 1 ? ' check' : ' checks'), '分析 ' + secs + ' 秒 · ' + tl.checks + ' 项核查')
      : L('Analyzed for ' + secs + 's', '分析 ' + secs + ' 秒');
    btn.appendChild(line); wrap.appendChild(btn);
    if (record.length) {
      var list = el('div', 'mmb-recap-list');
      list.id = 'mmb-recap-' + (++recapSeq);
      btn.setAttribute('aria-controls', list.id);
      record.forEach(function (r) { list.appendChild(thinkRow(r)); });
      wrap.appendChild(list);
      btn.addEventListener('click', function () {
        var on = wrap.classList.toggle('on');
        btn.setAttribute('aria-expanded', on ? 'true' : 'false');
        stick();   /* follow the growth only if the user is riding the bottom — never a jump pill */
      });
    }
    bub.insertBefore(wrap, bubTxt(bub));
    return wrap;
  }
  /* idempotent: stops the clock, drops the strip, and makes the holder inert. Called at
     every place the old `steps` node was removed (done, stop, error, abort). */
  function thinkTeardown(tl) {
    if (!tl || tl.dead) return;
    tl.dead = true;
    if (tl.timer) { clearInterval(tl.timer); tl.timer = 0; }
    if (tl.node.parentNode) tl.node.parentNode.removeChild(tl.node);
  }

  function newTurn(payload, typing) {
    /* `ub` is the user row THIS turn drew (null for a replay — regenerate/retry/resume
       paint no question of their own), so a retract can take back exactly what it put on
       screen and never a row that belongs to an earlier exchange. */
    return { payload: payload, typing: typing, bub: null, ub: null, stream: null, tl: null,
             suggestions: null, sawDelta: false, doneSeen: false, stopped: false, retracted: false,
             runId: null, threadId: null, cursor: 0, tries: 0, parks: 0 };
  }
  function ensureBub(T) {
    if (!T.bub) {
      if (T.typing && T.typing.parentNode) T.typing.remove();
      T.bub = appendMsg('assistant', ''); T.stream = MdStream(bubTxt(T.bub));
      markLastAssistant(); thinkMount(T.tl, T.bub);
    }
    return T.bub;
  }
  function endTurn(T) {
    /* A retract hands the prompt straight back to a focused composer, so "Stop, edit,
       send again" happens in a keystroke — and the aborted fetch's rejection lands AFTER
       that. Never let a straggler from a finished turn free the composer of the live one. */
    if (T && activeStream && activeStream !== T) return;
    streaming = false; streamAbort = null;
    if (activeStream === T) activeStream = null;
    setBusy(false); syncSend();
  }

  /* Parse one SSE event. Returns false for the `run` envelope (cursor must not move). */
  function handleEvent(j, T) {
    if (j.type === 'run') { T.runId = j.run_id; if (j.thread_id) T.threadId = j.thread_id; saveRun(T); return false; }
    T.tries = 0;   /* bytes are flowing again — reset the reconnect backoff */
    if (j.type === 'meta') { if (j.thread_id) { threadId = j.thread_id; T.threadId = j.thread_id; } if (j.quota) { quotas[j.quota.lane] = j.quota; renderQuota(); } }
    /* stage narration; anything arriving after `done` is stale noise */
    else if (j.type === 'status') { if (!T.doneSeen) thinkStatus(T.tl, j); }
    else if (j.type === 'tool') { ensureBub(T); if (!T.doneSeen) thinkTool(T.tl, j); stickAfter(); }
    /* A chart event no longer means "paste this picture": the widget draws the symbol
       itself from the published daily bars and keeps j.svg only as the fallback, so an
       older gateway (svg, no ticker) still renders exactly as before. */
    else if (j.type === 'chart' && (j.ticker || j.svg)) {
      ensureBub(T);
      mountChart(T.bub.querySelector('.mmb-charts') || T.bub, j);
      stickAfter();
    }
    else if (j.type === 'delta') {
      /* the answer has landed: the strip folds into the receipt above the text */
      ensureBub(T); thinkCollapse(T.tl, T.bub);
      /* The caret arrives WITH the first character, not with the bubble. A cursor parked
         under the ledger for the length of a 40s research pass is claiming to be typing
         while the answer is still buffered server-side — and it reads as a stray tick
         hanging off the bottom of the strip. */
      if (!T.sawDelta) T.stream.startCaret();
      T.sawDelta = true; T.bub._raw = (T.bub._raw || '') + j.text; T.stream.push(j.text);
    }
    else if (j.type === 'suggest') { if (j.items && j.items.length) T.suggestions = j.items.slice(0, 3); }
    /* host bridges (Terminal): chart-command + annotate events are executed by the
       host page, not the widget — forward them to the CFG callbacks when provided. */
    else if (j.type === 'command') { try { if (CFG.onCommand) CFG.onCommand(j); } catch (e) {} }
    else if (j.type === 'annotate') { try { if (CFG.onAnnotate) CFG.onAnnotate(j); } catch (e) {} }
    else if (j.type === 'done') { finalizeDone(j, T); }
    else if (j.type === 'error') {
      if (!T.sawDelta && !(T.bub && T.bub._raw)) { failTurn(T, j.message || ''); }
      else { ensureBub(T); T.bub._raw = (T.bub._raw || '') + '\n\n_' + (j.message || 'error') + '_'; T.stream.push('\n\n_' + (j.message || 'error') + '_'); }
    }
    return true;
  }
  function finalizeDone(j, T) {
    if (T.doneSeen) return; T.doneSeen = true;
    clearRun();
    ensureBub(T); thinkTeardown(T.tl);
    T.stream.finalize(function () {
      if (j && j.citations && j.citations.length) addCites(T.bub, j.citations);
      if (T.suggestions && T.suggestions.length) addSuggest(T.bub, T.suggestions);
      bumpTime(T.bub); stickAfter();
    });
    if (j && j.quota) { quotas[j.quota.lane] = j.quota; renderQuota(); }
  }
  /* Read an SSE body to its end, then decide what "end" meant (finished vs dropped). */
  function readSse(res, T) {
    var reader = res.body.getReader(), dec = new TextDecoder(), buf = '';
    function pump() {
      return reader.read().then(function (r) {
        if (r.done) { finish(T); return; }
        buf += dec.decode(r.value, { stream: true }); var lines = buf.split('\n'); buf = lines.pop() || '';
        lines.forEach(function (ln) {
          ln = ln.trim(); if (ln.indexOf('data:') !== 0) return; var data = ln.slice(5).trim(); if (!data) return;
          /* An unparseable event still occupies a slot in the server's buffer, so the
             cursor must advance past it — skipping the bump would desync us by one and
             make every later reconnect re-push the tail into the same bubble. */
          var j; try { j = JSON.parse(data); } catch (e) { T.cursor++; saveRun(T); return; }
          if (handleEvent(j, T)) { T.cursor++; saveRun(T); }
        });
        return pump();
      });
    }
    return pump();
  }
  function finish(T) {
    if (T.doneSeen || T.stopped) { endTurn(T); loadThreads(); announceDone(); return; }
    /* The stream ended without a `done`: the CONNECTION died, not the turn. */
    recover(T);
  }
  /* Re-attach with backoff. Stays "busy" throughout — from the user's side the reply
     is still being worked on, which is the truth. */
  var parked = null;   /* a turn waiting for the tab to come back to the foreground */
  function recover(T) {
    if (T.doneSeen || T.stopped) { endTurn(T); return; }
    if (!T.runId) { failTurn(T, ''); return; }            /* dropped before we had an id */
    /* A hidden tab is throttled and frequently offline. Retrying into that burns the
       whole budget in the first half-minute of an absence that may last an hour — so
       park instead, on a separate and BOUNDED counter. Unbounded parking would poll
       forever out of every abandoned tab; the timer is also the safety net for an
       embedding that reports hidden while perfectly visible, where a visibilitychange
       is never going to fire. Once the parks run out we SHELVE rather than fail: the
       stored record survives, so simply coming back to the tab picks the answer up. */
    if (DOC.hidden) {
      if (T.parks >= PARK_MAX) { shelve(T); return; }
      T.parks++; parked = T;
      setTimeout(function () {
        if (parked !== T || T.doneSeen || T.stopped) return;
        parked = null; attachRun(T);
      }, PARK_FALLBACK_MS);
      return;
    }
    if (T.tries >= RESUME_TRIES) { threadTail(T); return; }
    var wait = Math.min(8000, 500 * Math.pow(2, T.tries)); T.tries++;
    setTimeout(function () { if (!T.doneSeen && !T.stopped) attachRun(T); }, wait);
  }
  /* Stop FOLLOWING the turn without giving up on it: drop the spinner and free the
     composer, but leave the stored run alone so open()/visibilitychange can pick it
     back up from the server. Used when the tab has simply been away a long time. */
  function shelve(T) {
    T.stopped = true; parked = null;
    thinkTeardown(T.tl);
    if (T.typing && T.typing.parentNode) T.typing.remove();
    if (T.bub && T.stream && (T.sawDelta || T.bub._raw)) T.stream.finalize(function () { bumpTime(T.bub); stickAfter(); });
    else if (T.bub && T.bub.parentNode) T.bub.remove();   /* a bare "Reading…" bubble is noise */
    endTurn(T);
  }
  function attachRun(T) {
    var url = API + '/api/brain/runs/' + encodeURIComponent(T.runId) + '/stream?cursor=' + (T.cursor || 0);
    var ac = (typeof AbortController !== 'undefined') ? new AbortController() : null; streamAbort = ac;
    streaming = true; setBusy(true); activeStream = T;
    withAuth().then(function (h) { return fetch(url, { headers: h, credentials: 'include', signal: ac ? ac.signal : undefined }); })
      .then(function (res) {
        if (res.status === 404) { threadTail(T); return; }  /* expired, or the API restarted */
        if (!res.ok || !res.body) { recover(T); return; }
        return readSse(res, T);
      })
      .catch(function (err) {
        if (err && err.name === 'AbortError') { endTurn(T); return; }
        recover(T);
      });
  }
  /* Last resort before the error card: chat_stream persists BOTH turns to the thread,
     so even a run the registry has forgotten (API restart, past its TTL) left the
     answer behind. Paint the thread's tail if it is the reply we were waiting for. */
  function threadTail(T) {
    if (!threadId || guestMode) { failTurn(T, ''); return; }
    withAuth().then(function (h) { return fetch(API + '/api/brain/threads/' + encodeURIComponent(threadId), { headers: h, credentials: 'include' }); })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        var msgs = (d && d.messages) || [];
        var last = msgs.length ? msgs[msgs.length - 1] : null;
        if (!last || last.role !== 'assistant' || !last.content) { failTurn(T, ''); return; }
        /* Only accept the tail as OUR answer. The gateway writes the question first, so
           the turn before it must be this question — otherwise the assistant row is a
           previous exchange's and painting it under a new question would be a lie.
           (_append_message swallows its errors, so a dropped user write is possible.) */
        var q = (T.payload && T.payload.text) || '';
        var prev = msgs.length > 1 ? msgs[msgs.length - 2] : null;
        if (q && !(prev && prev.role === 'user' && String(prev.content || '').indexOf(q) === 0)) { failTurn(T, ''); return; }
        clearRun(); T.doneSeen = true;
        ensureBub(T); thinkTeardown(T.tl);
        T.bub._raw = last.content; T.stream.push(last.content);
        T.stream.finalize(function () { bumpTime(T.bub); stickAfter(); });
        endTurn(T); loadThreads(); announceDone();
      })
      .catch(function () { failTurn(T, ''); });
  }
  function failTurn(T, msg) {
    if (T.doneSeen) { endTurn(T); return; }
    T.doneSeen = true; clearRun(); parked = null;
    thinkTeardown(T.tl);
    if (T.typing && T.typing.parentNode) T.typing.remove();
    if (T.bub && T.stream && (T.sawDelta || T.bub._raw)) { T.stream.finalize(function () { bumpTime(T.bub); stickAfter(); }); }
    else {
      /* A bubble with only a "Reading …" step and no text is not a reply — drop it, or
         the error card stacks under a dead assistant slot. */
      if (T.bub && T.bub.parentNode) T.bub.remove();
      errorCard(T.payload, msg || '');
    }
    endTurn(T);
  }

  /* runStream(payload, showUser): runs one SSE turn. showUser=false skips drawing a new
     user bubble (used by regenerate — the user turn is already on screen). */
  function runStream(payload, showUser) {
    /* only the latest reply carries follow-up chips — clear any stale rows */
    root.querySelectorAll('.mmb-sugg').forEach(function (n) { n.remove(); });
    var ub = null;
    if (showUser) {
      ub = appendMsg('user', payload.text);
      if (payload.imgs && payload.imgs.length) {
        var iw = el('div', 'mmb-imgs');
        payload.imgs.forEach(function (s) { var im = el('img'); im.src = s; im.alt = ''; im.addEventListener('load', stickAfter); iw.appendChild(im); });
        ub.insertBefore(iw, ub.firstChild);
      }
    }
    sendBtn.disabled = true; streaming = true; upgradeEl.style.display = 'none';
    setBusy(true);
    var typing = el('div', 'mmb-msg assistant');
    typing.innerHTML = '<div class="mmb-bub"><span class="mmb-orbmark"><svg viewBox="0 0 24 24"><path d="' + ORB_PATH + '"/></svg></span></div>';
    scroll.appendChild(typing); stick();
    var T = newTurn(payload, typing);
    T.ub = ub;   /* what a retract may take back (see retractTurn) */
    /* the bouncing dots are replaced by the reasoning strip: it lives in the placeholder
       bubble until the real one exists, then moves across in ensureBub(). */
    T.tl = thinkInit(typing.querySelector('.mmb-bub'), payload.mode);
    activeStream = T;
    var apiText = payload.text || L('Please analyze the attached image.', '请分析所附图片。');
    var body = JSON.stringify({ message: apiText, lane: payload.lane, mode: payload.mode, thread_id: threadId || undefined, context: payload.ctx, images: (payload.imgs && payload.imgs.length) ? payload.imgs : undefined });
    if (streamAbort) { try { streamAbort.abort(); } catch (e) {} }
    var ac = (typeof AbortController !== 'undefined') ? new AbortController() : null; streamAbort = ac;
    withAuth({ 'Content-Type': 'application/json' }).then(function (h) {
      return fetch(API + '/api/brain/stream', { method: 'POST', headers: h, credentials: 'include', body: body, signal: ac ? ac.signal : undefined });
    }).then(function (res) {
      if (res.status === 401) { T.doneSeen = true; thinkTeardown(T.tl); if (typing.parentNode) typing.remove(); endTurn(T); if (window.MDXAuth && window.MDXAuth.enabled()) window.MDXAuth.open('signin'); else if (CFG.onAuthRequired) { try { CFG.onAuthRequired(); } catch (e) {} } return; }
      if (res.status === 402) { T.doneSeen = true; thinkTeardown(T.tl); if (typing.parentNode) typing.remove(); endTurn(T); return res.json().then(showUpgrade).catch(function () { showUpgrade({}); }); }
      if (!res.ok || !res.body) { failTurn(T, ''); return; }
      return readSse(res, T);
    }).catch(function (err) {
      /* AbortError = user pressed Stop; keep partial, no error card. Anything else is a
         dropped connection — recover() re-attaches before we ever claim the reply is lost. */
      if (err && err.name === 'AbortError') { endTurn(T); return; }
      recover(T);
    });
  }
  var activeStream = null;
  var recapSeq = 0;   /* unique ids so each receipt chip can aria-controls its own list */
  /* ── Stop = RETRACT (operator order) ─────────────────────────────────────────
     Before any of the answer has landed, Stop does not mean "halt and keep the scraps" —
     it UN-SENDS the turn. The run is cancelled server-side, everything this turn drew comes
     off the transcript (the placeholder/streaming bubble AND the user's own row), and the
     prompt goes back into the composer exactly as it was typed — text, images, caret at the
     end — because a user who stops this early is stopping to edit, not to read a fragment.
     The thread is left as if the turn had never been sent.

     Once text HAS arrived the answer belongs to the user: stopping then keeps what landed
     and tags it "· stopped" (the behaviour before this change), because silently deleting
     a reply someone is mid-way through reading would be the worse surprise. */
  function stopStream() {
    if (!streaming) return;
    var a = activeStream;
    if (a) a.stopped = true;
    parked = null;
    /* the strip stops with the stream; a receipt chip (delta already landed) stays put */
    if (a) thinkTeardown(a.tl);
    if (a && a.runId) {
      withAuth().then(function (h) { return fetch(API + '/api/brain/runs/' + encodeURIComponent(a.runId) + '/cancel', { method: 'POST', headers: h, credentials: 'include' }); }).catch(function () {});
    }
    clearRun();
    if (streamAbort) { try { streamAbort.abort(); } catch (e) {} }
    /* "landed" = at least one delta made it into a real bubble; a bubble that holds only
       the reasoning strip is not an answer and is retracted with the rest. */
    var landed = !!(a && a.bub && a.stream && (a.sawDelta || a.bub._raw));
    if (landed) {
      a.stream.stop();
      var txt = a.bub.querySelector('.mmb-txt') || a.bub;
      var s = el('span', 'mmb-stopped'); s.textContent = L(' · stopped', ' · 已停止'); txt.appendChild(s);
      bumpTime(a.bub); markLastAssistant();
    } else if (a) {
      retractTurn(a);
    }
    streaming = false; streamAbort = null; activeStream = null; setBusy(false); syncSend(); stickAfter();
  }
  /* Take one turn back off the screen. Idempotent (a second Stop, or a straggling abort
     handler, finds `retracted` already set and does nothing), and it only ever removes
     nodes THIS turn created: a replayed turn (regenerate / retry / resumed run) owns no
     user row, so its question stays exactly where it was. */
  var retractedAt = 0;   /* when the last retract landed — see the send-button click guard */
  function retractTurn(T) {
    if (!T || T.retracted) return;
    T.retracted = true;
    retractedAt = Date.now();
    if (T.stream) { try { T.stream.cancel(); } catch (e) {} }   /* drop the caret + any pending rAF */
    thinkTeardown(T.tl);                                        /* belt and braces: never leak the 1s clock */
    dropRow(T.typing);
    dropRow(T.bub);
    if (T.ub) {
      dropRow(T.ub);
      restoreComposer(T.payload);
      lastTurn = priorTurn; priorTurn = null;   /* Regenerate points at the previous turn again */
    }
    markLastAssistant();
    /* first turn of a fresh chat retracted → give the hero back rather than a blank panel */
    if (!scroll.querySelector('.mmb-msg')) renderEmpty();
  }
  /* Remove a message row from the transcript. Takes either the row itself or the bubble
     inside it, and is a no-op on anything already detached. */
  function dropRow(node) {
    if (!node) return;
    var row = (node.closest && node.closest('.mmb-msg')) || node;
    if (row && row.parentNode) row.parentNode.removeChild(row);
  }
  /* Put a retracted prompt back where it came from, ready to edit. A draft the user has
     ALREADY started typing while the turn was in flight is newer than the retracted one
     and wins — restoring over it would delete work they can see. */
  function restoreComposer(payload) {
    if (!payload) return;
    if (!ta.value.trim()) ta.value = payload.text || '';
    if (!pendingImages.length && payload.imgs && payload.imgs.length) {
      pendingImages = payload.imgs.slice(0, MAX_IMAGES); renderThumbs();
    }
    autosize(); syncSend(); updateCounter(); saveDraft();
    try { ta.focus(); var n = ta.value.length; ta.setSelectionRange(n, n); } catch (e) {}
  }

  /* ── pick a turn back up after the page went away ────────────────────────────
     Covers the reload/freeze case the reconnect above cannot: the tab was discarded,
     so there is no live turn to recover — only a run id in storage. Re-open the run's
     thread (which restores the question, persisted the moment it was accepted) and
     attach for the answer. A finished run needs no attach: the thread already has it. */
  var resuming = false;   /* open() and visibilitychange can both fire before the status
                             fetch lands; without this the turn attaches twice */
  function resumeStoredRun() {
    if (streaming || resuming || !panel.classList.contains('open')) return;
    var st = loadRun(); if (!st || !st.id) return;
    if (!st.ts || (Date.now() - st.ts) > RUN_MAX_AGE_MS) { clearRun(); return; }
    resuming = true;
    withAuth().then(function (h) { return fetch(API + '/api/brain/runs/' + encodeURIComponent(st.id), { headers: h, credentials: 'include' }); })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (s) {
        if (!s) { clearRun(); return; }        /* gone — the thread store is the record now */
        if (s.cancelled) { clearRun(); return; }
        if (s.thread_id) {
          if (s.done) { clearRun(); if (s.thread_id !== threadId) openThread(s.thread_id); return; }
          if (s.thread_id !== threadId) {
            /* `done:false` is a stale snapshot the moment we read it — the gateway
               writes the assistant row BEFORE the run flips done, and openThread costs
               another round-trip. So decide from what the thread actually contains: an
               assistant turn at the tail means the answer already landed and painting
               the replay too would double it. */
            openThread(s.thread_id, function (msgs) {
              var tail = (msgs && msgs.length) ? msgs[msgs.length - 1] : null;
              if (tail && tail.role === 'assistant') { clearRun(); return; }
              attachFresh(s, 0, st.q);
            });
            return;
          }
          attachFresh(s, st.cursor || 0, st.q);
          return;
        }
        /* Guest: nothing is persisted server-side, so replay the whole turn — question
           included, from the copy we kept when we sent it. */
        if (st.q) appendMsg('user', st.q);
        attachFresh(s, 0, st.q);
      })
      .catch(function () {})
      .then(function () { resuming = false; });
  }
  /* Build a fresh turn around an existing server run and attach to it. `question` is
     carried so a Retry on the error card can still replay the real turn. */
  function attachFresh(status, cursor, question) {
    root.querySelectorAll('.mmb-sugg').forEach(function (n) { n.remove(); });
    var typing = el('div', 'mmb-msg assistant');
    typing.innerHTML = '<div class="mmb-bub"><span class="mmb-orbmark"><svg viewBox="0 0 24 24"><path d="' + ORB_PATH + '"/></svg></span></div>';
    scroll.appendChild(typing); stick();
    var T = newTurn({ text: question || '', imgs: [], lane: status.lane || 'fast', mode: status.mode || 'chat' }, typing);
    /* replayed status events fast-forward the strip to the run's live stage */
    T.tl = thinkInit(typing.querySelector('.mmb-bub'), status.mode);
    T.runId = status.run_id; T.threadId = status.thread_id || null; T.cursor = cursor || 0;
    saveRun(T);   /* re-arm immediately — openThread() cleared the record on its way in */
    attachRun(T);
  }
  /* Coming back to the tab is the moment to act: a phone that froze the page never ran
     a single line of JS while it was away, and a parked turn has been waiting for this. */
  DOC.addEventListener('visibilitychange', function () {
    if (DOC.hidden) return;
    if (parked) { var p = parked; parked = null; p.tries = 0; if (!p.doneSeen && !p.stopped) attachRun(p); return; }
    resumeStoredRun();
  });
  /* Header busy dot + send↔stop button morph. The labels teach the two things that are
     not obvious from the glyph: how to send from the keyboard, and that Stop hands the
     message back rather than throwing it away. (title= stays English-only — house i18n
     law: a translated tooltip cannot follow the language toggle.) */
  function setBusy(on) {
    var dot = root.querySelector('.mmb-head .dot'); if (dot) dot.classList.toggle('busy', on);
    sendBtn.classList.toggle('mmb-stop', on);
    sendBtn.disabled = on ? false : ((!ta.value.trim() && !pendingImages.length));
    sendBtn.title = on ? 'Stop — puts your message back in the box' : ('Send (' + SEND_KEYS + ') — Enter starts a new line');
    sendBtn.setAttribute('aria-label', on
      ? L('Stop and put my message back', '停止并把消息退回输入框')
      : L('Send — ' + SEND_KEYS + '; Enter starts a new line', '发送 — ' + SEND_KEYS + '；回车换行'));
  }
  function bumpTime(bub) { var t = bub && bub.querySelector('.mmb-time'); if (t) t.textContent = relTime(t._ts); }
  /* Inline error card in the assistant slot with a Retry that replays the same payload. */
  function errorCard(payload, msg) {
    var d = el('div', 'mmb-msg assistant'); var b = el('div', 'mmb-bub');
    var orb = el('span', 'mmb-orbmark'); orb.innerHTML = '<svg viewBox="0 0 24 24"><path d="' + ORB_PATH + '"/></svg>'; b.appendChild(orb);
    var card = el('div', 'mmb-errcard');
    var line = el('div', 'mmb-errline'); line.textContent = L("The reply didn't make it through.", '回复没有送达。'); card.appendChild(line);
    var retry = el('button', 'mmb-retry'); retry.type = 'button';
    retry.innerHTML = ic('<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>') + '<span class="mmb-l" data-en="Retry" data-zh="重试">' + L('Retry', '重试') + '</span>';
    retry.setAttribute('aria-label', L('Retry', '重试'));
    retry.addEventListener('click', function () { if (streaming) return; d.remove(); runStream(payload, false); });
    card.appendChild(retry); b.appendChild(card); d.appendChild(b); scroll.appendChild(d); stickAfter();
  }
  /* a11y: announce completion once per done via the polite live region. */
  function announceDone() { try { var lr = $('#mmb-live'); if (lr) { lr.textContent = ''; lr.textContent = L('Reply finished', '回复完成'); } } catch (e) {} }
  /* follow-up suggestion chips — up to 3, appended after the latest assistant bubble.
     A click sends that question and removes the whole chip row (only the newest reply carries them). */
  function addSuggest(bub, items) {
    var wrap = DOC.createElement('div'); wrap.className = 'mmb-sugg';
    items.slice(0, 3).forEach(function (q, i) {
      if (!q) return;
      var btn = DOC.createElement('button'); btn.className = 'mmb-sug';
      btn.style.setProperty('--i', i);
      var g = DOC.createElement('span'); g.className = 'g'; g.textContent = '↳ ';
      btn.appendChild(g); btn.appendChild(DOC.createTextNode(String(q)));
      btn.addEventListener('click', function () { wrap.remove(); send(String(q)); });
      wrap.appendChild(btn);
    });
    if (wrap.childNodes.length) { insertBeforeActions(bub, wrap); stickAfter(); }
  }
  /* Cites/suggestions flow INSIDE the assistant content, above the action row. */
  function insertBeforeActions(bub, node) { var act = bub.querySelector('.mmb-actions'); if (act) bub.insertBefore(node, act); else bub.appendChild(node); }
  function addCites(bub, cites) {
    var wrap = DOC.createElement('div'); wrap.className = 'mmb-cites';
    cites.slice(0, 8).forEach(function (c) {
      var a = DOC.createElement('a'); a.className = 'mmb-cite'; a.textContent = String(c).replace(/\.(json|parquet)$/, '').split('/').pop();
      var page = citeToPage(c); if (page) { a.href = page; a.target = '_blank'; a.rel = 'noopener noreferrer'; }
      wrap.appendChild(a);
    });
    insertBeforeActions(bub, wrap); stickAfter();
  }
  function citeToPage(c) {
    c = String(c);
    if (/master_brief|world_state|regime/.test(c)) return (ANCHOR === 'top' ? 'https://www.mastermind-x.com/' : '') + 'macro.html';
    if (/options|gex|flow/.test(c)) return (ANCHOR === 'top' ? 'https://www.mastermind-x.com/' : '') + 'options_hub.html';
    if (/factor/.test(c)) return (ANCHOR === 'top' ? 'https://www.mastermind-x.com/' : '') + 'factors.html';
    return null;
  }
  function showUpgrade(d) {
    upgradeEl.style.display = 'block';
    var plansHref = (ANCHOR === 'top' ? 'https://www.mastermind-x.com/' : '') + 'plans.html';
    var link = '<a href="' + plansHref + '" target="_blank">' + LB('See plans', '查看套餐') + '</a>';
    /* Guests are prompted to SIGN IN (not to buy a plan) — signin is the natural next step,
       and it also unlocks the higher signed-in Fast cap. The link fires the MDXAuth signin. */
    var signinLink = '<a href="#" data-act="signin">' + LB('Sign in', '登录') + '</a>';
    if (guestMode && d && d.feature === 'pro') {
      upgradeEl.innerHTML = '<strong>' + LB('Sign in for Pro features', '登录以使用 Pro 功能') + '</strong> — ' +
        LB('Pro, Deep Research, and image attach need an account. ', 'Pro、深度研究与图片上传需要账户。') + signinLink;
    } else if (guestMode && d && (d.feature === 'quota' || !d.feature)) {
      upgradeEl.innerHTML = '<strong>' + LB("You've used today's free messages — sign in for more.", '今日免费次数已用完 — 登录以继续。') + '</strong> ' + signinLink;
    } else if (d && d.feature === 'vision') {
      upgradeEl.innerHTML = '<strong>' + LB('Image analysis is a Pro feature', '图像分析为 Pro 功能') + '</strong> — ' +
        LB('upgrade to attach charts and screenshots. ', '升级即可上传图表与截图。') + link;
    } else {
      upgradeEl.innerHTML = '<strong>' + LB('Quota reached', '配额已用尽') + '</strong> — ' +
        LB('upgrade to keep chatting. ', '升级以继续对话。') + link;
    }
  }

  /* ── lane + Deep Research ────────────────────────────────────────────────────
     One state machine, because the two controls describe the SAME choice: Deep
     Research runs on Pro (the gateway forces lane='pro' for mode='research'), so
     "Fast" and a lit Deep Research pill can never both be true. Picking Pro is a
     deliberate act — it costs Pro quota — so it is remembered rather than reset to
     Fast on the next page load. */
  function paintLane() {
    /* [data-lane] only — the third stop is Deep Research, and a blanket sweep over
       #mmb-lane button would strip the class paintResearch() had just put on it. */
    root.querySelectorAll('#mmb-lane button[data-lane]').forEach(function (b) {
      var on = b.dataset.lane === lane;
      b.classList.toggle('on', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
  }
  function paintResearch() { researchBtn.classList.toggle('on', researchMode); researchBtn.setAttribute('aria-pressed', researchMode ? 'true' : 'false'); }
  /* The composer says what the armed mode expects of it. A research pass is a question you
     ask once and come back to — not a one-line follow-up — and the box is the only surface
     that can say so at the moment it matters. Sourced from the data-ph-* pair when off, so
     a live language switch (relabel) still lands on the right default. */
  function paintPlaceholder() {
    ta.placeholder = researchMode
      ? L('Ask a research question — it comes back with a full write-up…', '提出一个研究问题 — 将返回完整研判…')
      : (zh() ? ta.getAttribute('data-ph-zh') : ta.getAttribute('data-ph-en'));
  }
  function setLane(next) {
    lane = next === 'pro' ? 'pro' : 'fast';
    if (lane === 'fast' && researchMode) researchMode = false;   /* mutually exclusive */
    paintLane(); paintResearch(); paintPlaceholder(); savePrefs(); renderQuota();
  }
  function setResearch(on) {
    researchMode = !!on;
    if (researchMode) lane = 'pro';                              /* research IS the Pro lane */
    paintLane(); paintResearch(); paintPlaceholder(); savePrefs(); renderQuota();
  }

  /* Lane + Deep Research are USER choices, not per-page defaults. The widget is
     re-constructed on every navigation of a static multi-page site (and on every
     reload), so without this a Pro user is silently dropped back to Fast the moment
     they move pages — the "it flips back to Fast after every answer" complaint.
     Restored only once /api/brain/me confirms Pro eligibility, so a lapsed account
     is never left pointing at a lane it can no longer use.

     The LANE is remembered; Deep Research is NOT. The lane is a standing preference
     ("I'm a Pro user, answer me properly"), but research is an intent about one
     question — it costs a Pro credit and takes minutes, and silently re-arming it on
     the next page so a one-line follow-up runs as a research report is not a
     preference, it is a surprise bill. */
  var PREF_KEY = 'mm.brain.prefs';
  function savePrefs() {
    try { localStorage.setItem(PREF_KEY, JSON.stringify({ lane: lane })); } catch (e) {}
  }
  function restorePrefs() {
    if (!proEligible) {
      if (lane === 'pro' || researchMode) { lane = 'fast'; researchMode = false; paintLane(); paintResearch(); savePrefs(); }
      return;
    }
    var p = null; try { p = JSON.parse(localStorage.getItem(PREF_KEY) || 'null'); } catch (e) {}
    if (!p) return;
    lane = p.lane === 'pro' ? 'pro' : 'fast';
    paintLane();
  }
  function autosize() { ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight, 150) + 'px'; }

  /* ── widget mechanics ── */
  /* Always open COMPACT (operator order): dashboard = corner chatbox, Terminal = top
     drop-down. The expand button offers the large overlay — desktop only. */
  function open() {
    refreshCtx(); scrim.classList.add('open'); panel.classList.add('open');
    if (ANCHOR === 'top') panel.classList.add('mmb-top');
    if (launch) { launch.classList.add('mmb-hide'); launch.setAttribute('aria-expanded', 'true'); }
    /* WAAPI entry (transform only; opacity fades via CSS) — the sole transform owner. */
    if (!reduceMotion() && typeof panel.animate === 'function') {
      if (panel._morph) { try { panel._morph.cancel(); } catch (e) {} }
      var fy = ANCHOR === 'top' ? -16 : 16;
      panel._morph = panel.animate(
        [{ transform: 'translateY(' + fy + 'px) scale(.98)' }, { transform: 'none' }],
        { duration: 360, easing: MORPH_EASE, fill: 'none' }
      );
    }
    if (authed) { loadThreads(); loadQuotas(); }
    else { loadQuotas(); }   /* guests refresh their daily meter; a 401 keeps the gate */
    restoreDraft();
    resumeStoredRun();       /* a turn started before a reload is still ours to finish */
    setTimeout(focusPanel, 260);
  }
  /* Move focus INTO the panel once the entry has settled. It cannot just be ta.focus():
     for a SIGNED-OUT visitor the composer is display:none and the sign-in gate stands in
     its place, so that call is a silent no-op and focus is left stranded on <body> — the
     keyboard user who just pressed Enter would Tab from the top of the page instead of
     into the chat they opened. Take the composer when it is live, the gate's own primary
     action when it is not, and the first thing the panel is actually showing otherwise. */
  function focusPanel() {
    var cands = [ta, $('.mmb-signin')].concat(
      [].slice.call(panel.querySelectorAll('button:not([disabled]),a[href],textarea,[tabindex="0"]')));
    for (var i = 0; i < cands.length; i++) {
      var n = cands[i];
      if (!n || !n.offsetParent) continue;     /* display:none somewhere up the chain */
      try { n.focus(); } catch (e) { continue; }
      if (DOC.activeElement === n) return;
    }
  }
  /* Tear down any in-flight stream: abort the fetch reader, drop the caret, and reset the
     streaming flags + send button. Called by newChat/openThread so switching context
     mid-stream never leaves the composer wedged (streaming stuck true → send disabled).
     `stopped` suppresses the reconnect — this is a deliberate context switch, not a lost
     connection — and the stored run is dropped so the widget does not later yank the user
     back to a turn they navigated away from. The RUN itself keeps going server-side and
     still lands in its own thread; nothing is thrown away, it just stops following us. */
  function abortStream() {
    if (activeStream) activeStream.stopped = true;
    parked = null; clearRun();
    if (!streaming && !streamAbort) { activeStream = null; return; }
    if (streamAbort) { try { streamAbort.abort(); } catch (e) {} streamAbort = null; }
    if (activeStream && activeStream.stream) { try { activeStream.stream.cancel(); } catch (e) {} }
    if (activeStream) thinkTeardown(activeStream.tl);
    activeStream = null; streaming = false; setBusy(false);
  }
  /* Closing the panel does NOT tear the turn down — the widget is hidden, not gone, and
     the answer keeps painting into it. Re-opening shows the finished reply. */
  function close() {
    if (panel._morph) { try { panel._morph.cancel(); } catch (e) {} }
    /* Read activeElement BEFORE the classes drop: the panel goes visibility:hidden on the
       way out, and the browser blurs whatever was focused inside it the moment it does. */
    var wasInside = root.contains(DOC.activeElement);
    scrim.classList.remove('open', 'max'); panel.classList.remove('open', 'max', 'show-side');
    if (launch) {
      launch.classList.remove('mmb-hide'); launch.setAttribute('aria-expanded', 'false');
      /* Hand focus back to the control that opened it — otherwise a keyboard user who
         closes with Esc is stranded on <body> and tabs from the top of the page again.
         Only when focus was ours to begin with, so a scrim click never steals it. */
      if (wasInside) { try { launch.focus(); } catch (e) {} }
    }
  }
  function toggle() { panel.classList.contains('open') ? close() : open(); }
  /* ── FLIP morph: animate the compact↔max resize with a transform ONLY (GPU compositor,
     60fps, zero reflow). Measure First rect → apply the class (panel snaps to Last geometry)
     → Invert with an instant transform so it still LOOKS like First → Play the transform back
     to identity with a premium long-tail ease. ── */
  var MORPH_EASE = 'cubic-bezier(.22,1,.36,1)';
  function reduceMotion() { try { return matchMedia('(prefers-reduced-motion:reduce)').matches; } catch (e) { return false; } }
  function flipMorph(mutate) {
    // Web Animations API FLIP: mutate to the final geometry, then play a transform-only
    // animation from an inverse (that makes it LOOK like the start) back to identity.
    // fill:'none' auto-reverts to the CSS resting transform on finish — no transitionend
    // to miss, no stuck inline transform; cancelable so rapid toggles never fight.
    if (reduceMotion() || typeof panel.animate !== 'function') { mutate(); return; }
    var first = panel.getBoundingClientRect();
    mutate();                                   // panel jumps to its final geometry
    var last = panel.getBoundingClientRect();
    var dx = first.left - last.left, dy = first.top - last.top;
    var sx = last.width ? first.width / last.width : 1;
    var sy = last.height ? first.height / last.height : 1;
    if (!isFinite(sx) || !isFinite(sy) || (Math.abs(dx) < 1 && Math.abs(dy) < 1 && Math.abs(sx - 1) < 0.01 && Math.abs(sy - 1) < 0.01)) return;
    if (panel._morph) { try { panel._morph.cancel(); } catch (e) {} }
    var invert = 'translate(' + dx.toFixed(2) + 'px,' + dy.toFixed(2) + 'px) scale(' + sx.toFixed(5) + ',' + sy.toFixed(5) + ')';
    panel._morph = panel.animate(
      [{ transformOrigin: 'top left', transform: invert },
       { transformOrigin: 'top left', transform: 'none' }],
      { duration: 480, easing: MORPH_EASE, fill: 'none' }
    );
  }
  function toggleMax() {
    if (window.innerWidth <= 560) return;       // mobile is compact-only
    flipMorph(function () {
      var max = panel.classList.toggle('max');
      panel.classList.remove('show-side');
      scrim.classList.toggle('max', max);
      if (max) panel.classList.remove('mmb-top');
      else if (ANCHOR === 'top') panel.classList.add('mmb-top');
    });
  }
  function toggleSide() { panel.classList.toggle('show-side'); }
  function newChat() { abortStream(); threadId = null; pendingImages = []; renderThumbs(); root.querySelectorAll('.mmb-ti').forEach(function (el) { el.classList.remove('on'); }); clearMsgs(); ta.value = ''; autosize(); syncSend(); updateCounter(); closeSlash(); restoreDraft(); if (!panel.classList.contains('max')) panel.classList.remove('show-side'); }

  /* ── auth wiring ── */
  function onAuth(user) {
    authed = !!user;
    var gate = $('#mmb-gate');
    if (authed) {
      guestMode = false;
      if (gate) gate.remove();
      if (!scroll.querySelector('.mmb-msg') && !$('#mmb-emptystate')) renderEmpty();
      if (panel.classList.contains('open')) { loadThreads(); loadQuotas(); }
      showChat(true);
    } else {
      /* Signed out: default to the gate, then probe /api/brain/me — if guest access is on it
         returns tier 'guest' and enterGuest() flips to the chat UI. */
      showChat(false);
      loadQuotas();
    }
  }
  function showChat(on) {
    var comp = root.querySelector('.mmb-comp'); comp.style.display = on ? '' : 'none'; scroll.style.display = on ? '' : 'none';
    var gate = $('#mmb-gate');
    if (!on && !gate) {
      var g = DOC.createElement('div'); g.id = 'mmb-gate'; g.className = 'mmb-gate';
      g.innerHTML = '<div class="mmb-orb">' + ORB + '</div><h2>' + LB('Ask the Mastermind', '问操盘大脑') + '</h2>' +
        '<p>' + LB('One brain across every dashboard and the Terminal. Sign in to begin.', '贯通所有看板与终端的同一个大脑。登录即可开始。') + '</p>' +
        '<button class="mmb-signin" data-act="signin">' + LB('Sign in', '登录') + '</button>';
      root.querySelector('.mmb-main').insertBefore(g, root.querySelector('.mmb-comp'));
    } else if (on && gate) gate.remove();
  }
  /* Guest mode: signed-out but allowed the free Fast lane. Show the chat UI (not the gate),
     render a sign-in prompt in the threads panel (guests are stateless), and load quotas. */
  function enterGuest(on) {
    if (on === guestMode) { if (on) { renderEmpty(); showChat(true); } return; }
    guestMode = on;
    if (on) {
      var gate = $('#mmb-gate'); if (gate) gate.remove();
      if (!scroll.querySelector('.mmb-msg') && !$('#mmb-emptystate')) renderEmpty();
      showChat(true);
      paintGuestThreads();
    } else {
      showChat(false);
    }
  }
  /* Threads panel body for guests — conversations aren't saved, so offer sign-in instead. */
  function paintGuestThreads() {
    if (!tlist) return;
    tlist.innerHTML = '<div class="mmb-th-empty" style="display:flex;flex-direction:column;gap:10px;align-items:flex-start">' +
      '<span>' + LB('Sign in to save your conversations.', '登录后可保存对话记录。') + '</span>' +
      '<button class="mmb-signin" data-act="signin" style="margin-top:0;padding:9px 18px;font-size:13px">' + LB('Sign in', '登录') + '</button></div>';
  }

  /* ── events (delegated) ── */
  root.addEventListener('click', function (e) {
    var rm = e.target.closest('[data-rmimg]');
    if (rm) { pendingImages.splice(+rm.dataset.rmimg, 1); renderThumbs(); return; }
    var t = e.target.closest('[data-act],[data-p],[data-lane]'); if (!t) return;
    if (t.dataset.p) { ta.value = t.dataset.p; autosize(); send(); return; }
    if (t.dataset.lane) {
      /* Guests: the Pro lane is a sign-in prompt (it stays locked); Fast is theirs. */
      if (t.dataset.lane === 'pro' && guestMode) { showUpgrade({ feature: 'pro' }); return; }
      setLane(t.dataset.lane); return;
    }
    var a = t.dataset.act;
    if (a === 'close') close(); else if (a === 'max') toggleMax(); else if (a === 'side') toggleSide();
    else if (a === 'new') newChat();
    else if (a === 'research') { if (guestMode) showUpgrade({ feature: 'pro' }); else setResearch(!researchMode); }
    else if (a === 'home') location.href = (ANCHOR === 'top' ? 'https://www.mastermind-x.com/' : '') + 'macro.html';
    else if (a === 'search') toggleSearch();
    else if (a === 'search-clear') { searchIn.value = ''; paintThreads(); searchIn.focus(); }
    else if (a === 'voice') startVoice();
    else if (a === 'attach') { if (proEligible) fileEl.click(); else showUpgrade(guestMode ? { feature: 'pro' } : { feature: 'vision' }); }
    else if (a === 'signin') { e.preventDefault(); if (window.MDXAuth) window.MDXAuth.open('signin'); }
  });
  fileEl.addEventListener('change', function () { addFiles(fileEl.files); fileEl.value = ''; });
  /* ── drag & drop ──────────────────────────────────────────────────────────────
     dragenter/dragleave fire for every child the pointer crosses, so a naive
     leave-hides-it never survives the first hop between two nodes — the overlay would
     strobe. Depth counting is the fix: the drag is over us until as many leaves as
     enters have landed. `dragover` must preventDefault or the browser navigates to the
     dropped file and takes the whole conversation with it. */
  (function wireDrop() {
    var depth = 0;
    function hasFiles(e) {
      var dt = e.dataTransfer; if (!dt) return false;
      if (dt.types) for (var i = 0; i < dt.types.length; i++) if (dt.types[i] === 'Files') return true;
      return false;
    }
    function show(on) { panel.classList.toggle('dropping', !!on); if (!on) depth = 0; }
    panel.addEventListener('dragenter', function (e) {
      if (!hasFiles(e)) return;
      e.preventDefault(); depth++; show(true);
    });
    panel.addEventListener('dragover', function (e) {
      if (!hasFiles(e)) return;
      e.preventDefault();
      try { e.dataTransfer.dropEffect = 'copy'; } catch (err) {}
    });
    panel.addEventListener('dragleave', function (e) {
      if (!hasFiles(e)) return;
      depth = Math.max(0, depth - 1);
      if (!depth) show(false);
    });
    panel.addEventListener('drop', function (e) {
      if (!hasFiles(e)) return;
      e.preventDefault(); show(false);
      /* same gate as the paperclip: attaching images is a Pro capability, and finding
         that out from a 402 after the upload is the worse way to learn it */
      if (!proEligible) { showUpgrade(guestMode ? { feature: 'pro' } : { feature: 'vision' }); return; }
      addFiles(e.dataTransfer.files);
      try { ta.focus(); } catch (err) {}
    });
    /* a drag that ends outside the window never fires drop or leave on us */
    window.addEventListener('dragend', function () { show(false); });
    window.addEventListener('drop', function (e) { if (!panel.contains(e.target)) show(false); });
  })();
  if (searchIn) {
    searchIn.addEventListener('input', paintThreads);
    searchIn.addEventListener('keydown', function (e) { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); toggleSearch(false); } });
  }
  /* follow the host's language switch live — dashboard fires 'langchange' on the
     document (theme.js setLang), the Terminal fires 'mm:lang' on window (i18n.tsx). */
  DOC.addEventListener('langchange', relabel);
  window.addEventListener('mm:lang', relabel);
  if (launch) {
    launch.addEventListener('click', open);
    /* role="button" buys the semantics; the keys are still ours to wire. Space is
       preventDefault'd or the page scrolls away underneath the panel that just opened. */
    launch.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' && e.key !== ' ' && e.key !== 'Spacebar') return;
      e.preventDefault();
      open();
    });
  }
  scrim.addEventListener('click', close);
  /* Send button doubles as Stop mid-stream (the arrow morphs to a square). A retract
     flips it straight back to Send with the prompt reloaded, so the SECOND half of an
     impatient double-click would otherwise re-send what the first half took back. */
  sendBtn.addEventListener('click', function () {
    if (streaming) { stopStream(); return; }
    if (Date.now() - retractedAt < 400) return;   /* the tail of a double-click on Stop */
    send();
  });
  ta.addEventListener('input', function () { autosize(); syncSend(); updateCounter(); slashSync(); saveDraft(); });
  /* ── composer keys ───────────────────────────────────────────────────────────
     Enter writes a NEW LINE (operator order: the box is for multi-line prompts first);
     sending is ⌘/Ctrl+Enter, Shift+Enter, or the button.
     IME first, before every other branch: a Chinese/Japanese/Korean user presses Enter to
     ACCEPT a candidate, and that keystroke must never reach send() — `isComposing` is the
     modern signal, keyCode 229 the legacy one that older WebKit/Android IMEs still use.
     A composition Enter is not ours at all: we do not preventDefault it either, we simply
     hand it back to the input method. */
  function composing(e) { return !!(e.isComposing || e.keyCode === 229 || e.which === 229); }
  ta.addEventListener('keydown', function (e) {
    if (composing(e)) return;                                // the IME candidate window owns this key
    if (slashKeydown(e)) return;                             // palette owns ↑/↓/Enter/Esc while open
    if (e.key !== 'Enter') return;
    if (e.metaKey || e.ctrlKey || e.shiftKey) { e.preventDefault(); send(); return; }
    /* plain Enter: fall through untouched — the textarea inserts its own newline */
  });
  ta.addEventListener('paste', function (e) { /* paste a screenshot straight in */
    var items = (e.clipboardData && e.clipboardData.items) || []; var files = [];
    for (var i = 0; i < items.length; i++) { if (items[i].type && items[i].type.indexOf('image/') === 0) { var f = items[i].getAsFile(); if (f) files.push(f); } }
    if (files.length) { e.preventDefault(); addFiles(files); }
  });
  /* Single Esc chain (priority): slash palette → stream → search → close. */
  DOC.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape' || !panel.classList.contains('open')) return;
    if (slashOpen()) { e.preventDefault(); closeSlash(); return; }
    if (streaming) { e.preventDefault(); stopStream(); return; }
    if (searchWrap && searchWrap.classList.contains('on')) { e.preventDefault(); toggleSearch(false); return; }
    e.preventDefault(); close();
  });
  /* Scroll pinning: any upward move (wheel/touch/scroll away from bottom) unpins;
     returning to the bottom re-pins and clears the jump pill. */
  scroll.addEventListener('scroll', function () { if (atBottom()) { pinned = true; hideJump(); } else { pinned = false; } }, { passive: true });
  scroll.addEventListener('wheel', function (e) { if (e.deltaY < 0) pinned = false; }, { passive: true });
  scroll.addEventListener('touchmove', function () { if (!atBottom()) pinned = false; }, { passive: true });

  /* ── vision: attach + downscale images ── */
  function addFiles(files) {
    var arr = [].slice.call(files || []);
    arr.forEach(function (f) {
      if (!/^image\//.test(f.type) || pendingImages.length >= MAX_IMAGES) return;
      downscaleImage(f).then(function (dataUri) {
        if (!dataUri || pendingImages.length >= MAX_IMAGES) return;
        pendingImages.push(dataUri); renderThumbs();
      }).catch(function () {});
    });
  }
  /* draw to a canvas capped at 1024px longest side, re-encode JPEG q0.82 → small data URI */
  function downscaleImage(file) {
    return new Promise(function (resolve, reject) {
      var fr = new FileReader();
      fr.onload = function () {
        var img = new Image();
        img.onload = function () {
          var max = 1024, w = img.width, h = img.height;
          if (w > max || h > max) { var s = Math.min(max / w, max / h); w = Math.round(w * s); h = Math.round(h * s); }
          try {
            var cv = DOC.createElement('canvas'); cv.width = w; cv.height = h;
            cv.getContext('2d').drawImage(img, 0, 0, w, h);
            resolve(cv.toDataURL('image/jpeg', 0.82));
          } catch (e) { resolve(fr.result); }
        };
        img.onerror = reject; img.src = fr.result;
      };
      fr.onerror = reject; fr.readAsDataURL(file);
    });
  }
  function renderThumbs() {
    if (!pendingImages.length) { thumbsEl.className = 'mmb-thumbs'; thumbsEl.innerHTML = ''; syncSend(); return; }
    thumbsEl.className = 'mmb-thumbs on'; thumbsEl.innerHTML = '';
    pendingImages.forEach(function (src, i) {
      var d = DOC.createElement('div'); d.className = 'mmb-thumb'; d.style.setProperty('--i', i);
      /* set src via the DOM property (never interpolate a data URI into innerHTML) */
      var im = DOC.createElement('img'); im.src = src; im.alt = '';
      var x = DOC.createElement('button'); x.className = 'x'; x.setAttribute('data-rmimg', i); x.title = 'Remove'; x.textContent = '✕';
      d.appendChild(im); d.appendChild(x); thumbsEl.appendChild(d);
    });
    syncSend();
  }
  /* send is enabled when there's text OR at least one attached image (and not mid-stream) */
  function syncSend() {
    sendBtn.disabled = (!ta.value.trim() && !pendingImages.length) || streaming;
    /* the ⌘↵ hint shows exactly while there is something to send — which is also the
       moment a user is about to press Enter and expect it to go. */
    if (boxEl) boxEl.classList.toggle('mmb-typing', !sendBtn.disabled);
  }

  /* ── voice (best-effort Web Speech) ── */
  function voiceSupported() { return !!(window.SpeechRecognition || window.webkitSpeechRecognition); }
  function startVoice() {
    var SR = window.SpeechRecognition || window.webkitSpeechRecognition; if (!SR) return;
    var r = new SR(); r.lang = zh() ? 'zh-CN' : 'en-US'; r.interimResults = false;
    r.onresult = function (ev) { ta.value = (ta.value + ' ' + ev.results[0][0].transcript).trim(); autosize(); syncSend(); updateCounter(); };
    try { r.start(); } catch (e) {}
  }
  /* Hide the mic entirely where Web Speech is unsupported (rather than a dead button). */
  (function () { if (!voiceSupported()) { var vb = root.querySelector('[data-act="voice"]'); if (vb) vb.style.display = 'none'; } })();

  /* ── char counter (muted, appears near the cap) ── */
  var MAXLEN = 2000;
  function updateCounter() {
    var n = ta.value.length;
    if (n > 1800) { qEl.classList.add('mmb-count'); qEl.textContent = n + ' / ' + MAXLEN; qEl.classList.toggle('warn', n > 1950); qEl.classList.remove('empty'); qEl.removeAttribute('title'); }
    else if (qEl.classList.contains('mmb-count')) { qEl.classList.remove('mmb-count', 'warn'); renderQuota(); }
  }

  /* ── drafts (persist composer text per thread) ── */
  function draftKey() { return 'mmb_draft_' + (threadId || 'new'); }
  var draftTimer = 0;
  function saveDraft() {
    if (draftTimer) clearTimeout(draftTimer);
    draftTimer = setTimeout(function () {
      try { var v = ta.value; if (v) localStorage.setItem(draftKey(), v); else localStorage.removeItem(draftKey()); } catch (e) {}
    }, 400);
  }
  function clearDraft() { try { localStorage.removeItem(draftKey()); } catch (e) {} }
  function restoreDraft() {
    try { var v = localStorage.getItem(draftKey()); if (v && !ta.value) { ta.value = v; autosize(); syncSend(); updateCounter(); } } catch (e) {}
  }

  /* ── slash palette (typing "/" as the first char) ────────────────────────────
     A 3-item glass menu above the composer. ↑/↓ move, Enter/click select, Esc or
     backspace-to-empty closes. Each item inserts a templated prompt (ZH variants). */
  var slashEl = null, slashItems = [], slashIdx = 0;
  function slashDefs() {
    var sym = ctxSymbol || 'AAPL';
    return [
      { key: 'chart', icon: '<path d="M3 3v18h18"/><path d="M7 14l4-4 3 3 5-6"/>', name: LB('/chart', '/图表'), hint: LB('Map structure, levels & what to watch', '结构、关键位与关注点'),
        run: function () { insertText(L('Map the structure on ' + sym + ' — trend, key levels, and what to watch.', '梳理 ' + sym + ' 的结构 — 趋势、关键价位与需关注之处。')); } },
      { key: 'research', icon: '<path d="M12 3v3M12 18v3M3 12h3M18 12h3M6 6l2 2M16 16l2 2M18 6l-2 2M8 16l-2 2"/>', name: LB('/research', '/研究'), hint: LB('Deep-dive with Deep Research', '开启深度研究'),
        run: function () { if (proEligible) { if (!researchMode) setResearch(true); insertText(L('Deep-dive: ', '深度研究：')); } else { closeSlash(); showUpgrade(guestMode ? { feature: 'pro' } : {}); } } },
      { key: 'explain', icon: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3 2.4c-.6.2-1 .8-1 1.6M12 17h.01"/>', name: LB('/explain', '/解释'), hint: LB('Read this page right now', '解读当前页面'),
        run: function () { insertText(L('Explain this page — what is it telling me right now?', '解读这个页面 — 它现在告诉我什么？')); } }
    ];
  }
  function insertText(t) { closeSlash(); ta.value = t; autosize(); ta.focus(); syncSend(); updateCounter(); saveDraft(); }
  function slashOpen() { return !!slashEl; }
  function openSlash() {
    if (slashEl) return;
    slashItems = slashDefs(); slashIdx = 0;
    slashEl = el('div', 'mmb-slash');
    slashItems.forEach(function (it, i) {
      var b = el('button', 'mmb-slash-i' + (i === 0 ? ' on' : '')); b.type = 'button'; b.dataset.i = i;
      b.innerHTML = '<span class="si">' + ic(it.icon) + '</span><span class="sn">' + it.name + '</span><span class="sh">' + it.hint + '</span>';
      b.addEventListener('mouseenter', function () { slashIdx = i; paintSlash(); });
      b.addEventListener('click', function (e) { e.preventDefault(); it.run(); });
      slashEl.appendChild(b);
    });
    root.querySelector('.mmb-box').insertBefore(slashEl, root.querySelector('.mmb-box').firstChild);
  }
  function paintSlash() { if (!slashEl) return; [].forEach.call(slashEl.children, function (c, i) { c.classList.toggle('on', i === slashIdx); }); }
  function closeSlash() { if (slashEl) { slashEl.remove(); slashEl = null; slashItems = []; } }
  /* open when the field starts with "/" and is a single token; close otherwise */
  function slashSync() {
    var v = ta.value;
    if (v.charAt(0) === '/' && v.indexOf('\n') === -1 && v.indexOf(' ') === -1) openSlash();
    else closeSlash();
  }
  function slashKeydown(e) {
    if (!slashEl) return false;
    if (e.key === 'ArrowDown') { e.preventDefault(); slashIdx = (slashIdx + 1) % slashItems.length; paintSlash(); return true; }
    if (e.key === 'ArrowUp') { e.preventDefault(); slashIdx = (slashIdx - 1 + slashItems.length) % slashItems.length; paintSlash(); return true; }
    if (e.key === 'Enter') { e.preventDefault(); slashItems[slashIdx].run(); return true; }
    if (e.key === 'Escape') { e.preventDefault(); closeSlash(); return true; }
    if (e.key === 'Backspace' && ta.value.length <= 1) { closeSlash(); return false; }
    return false;
  }

  /* ── context (active ticker) ── */
  function refreshCtx() {
    var s = ''; try { s = (CFG.symbol && CFG.symbol()) || window.MDXActiveSymbol || window.MMBrainSymbol || window.ACTIVE_SYMBOL || ''; } catch (e) {}
    var m = /[?&]symbol=([A-Za-z0-9.\-:]+)/i.exec(location.search); if (!s && m) s = m[1];
    ctxSymbol = (s || '').toString().toUpperCase().slice(0, 24);
    if (ctxSymbol) { ctxEl.className = 'mmb-ctx on'; ctxEl.innerHTML = '<span class="chip" title="Active symbol"><svg class="cx" viewBox="0 0 24 24"><circle cx="12" cy="12" r="6.5"/><circle cx="12" cy="12" r="1.7" fill="currentColor" stroke="none"/></svg><b>' + esc(ctxSymbol) + '</b></span>'; }
    else ctxEl.className = 'mmb-ctx';
  }
  refreshCtx(); renderEmpty();
  setBusy(false);   /* bake the send button's shortcut label once at boot, not on first stream */

  /* ── "explain this panel" — public entry + card affordance ── */
  /* opens the widget compact (never forced to max) and asks the Brain to read the panel.
     The panel key rides along once in the next send()'s context (ctx.panel). */
  function explain(key, title) {
    explainPanel = key;
    if (!panel.classList.contains('open')) open();
    panel.classList.remove('max');
    var t = title || key;
    send(L('Explain the "' + t + '" panel — what is it showing right now, and what should I do about it?',
           '解释「' + t + '」面板 — 它现在显示什么？我该怎么做？'));
  }
  /* inject a hover "ask the Brain" orb into each dashboard island card face.
     No-op on pages without .sx island cards (Terminal, plain pages). */
  function initExplain() {
    var faces = root.ownerDocument ? DOC.querySelectorAll('.sx[id^="sx-"] .mx5-card-face, .sx[id^="sx-"] .sxg-face') : [];
    var seen = [];
    [].forEach.call(faces, function (face) {
      var host = face.closest('.sx[id^="sx-"]'); if (!host || seen.indexOf(host) >= 0) return; seen.push(host);
      if (face.querySelector('.mmb-exp')) return; /* one per host */
      var cs = (DOC.defaultView || window).getComputedStyle(face);
      if (cs && cs.position === 'static') face.style.position = 'relative';
      var btn = DOC.createElement('button'); btn.className = 'mmb-exp'; btn.type = 'button'; btn.title = 'Ask the Brain';
      btn.innerHTML = '<svg viewBox="0 0 24 24"><path d="' + ORB_PATH + '"/></svg>';
      btn.addEventListener('click', function (e) {
        e.stopPropagation(); e.preventDefault();
        var key = host.id.replace(/^sx-/, '');
        var tEl = host.querySelector('.mx5-card-title');
        var title = (tEl && tEl.textContent.trim()) || key;
        explain(key, title);
      });
      face.appendChild(btn);
    });
  }

  /* ── boot ── */
  function boot() {
    if (window.MDXAuth) { window.MDXAuth.onChange(onAuth); }
    else window.addEventListener('load', function () { if (window.MDXAuth) window.MDXAuth.onChange(onAuth); else { authed = true; showChat(true); } });
  }
  boot();
  initExplain();

  window.MMBrain = { open: open, close: close, toggle: toggle, explain: explain,
    expand: function () { var was = panel.classList.contains('open'); if (!was) open(); if (window.innerWidth > 560 && !panel.classList.contains('max')) setTimeout(toggleMax, was ? 0 : 80); },
    mounted: true };
})();
