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

  /* ── CSS ─────────────────────────────────────────────────────────────── */
  var CSS = `
  #mmb-root{--mmb-info:#5b9bf0;--mmb-violet:#8b5cf6;--mmb-text:#e6eaf0;--mmb-muted:#8b93a1;
    --mmb-panel:#181b21;--mmb-panel2:#1e222a;--mmb-line:color-mix(in srgb,#fff 9%,transparent);
    --mmb-font:Inter,-apple-system,"Segoe UI",Roboto,sans-serif}
  #mmb-root *{box-sizing:border-box}
  /* launcher (bottom-right) */
  #mmb-launch{position:fixed;right:22px;bottom:22px;z-index:2147483000;display:flex;align-items:center;gap:10px;
    padding:8px 16px 8px 8px;border-radius:999px;cursor:pointer;border:1px solid var(--mmb-line);font-family:var(--mmb-font);
    background:color-mix(in srgb,var(--mmb-panel) 82%,transparent);-webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px);
    box-shadow:0 12px 40px -12px rgba(0,0,0,.6),0 0 0 1px color-mix(in srgb,var(--mmb-info) 12%,transparent);
    transition:transform .18s ease,box-shadow .18s ease}
  #mmb-launch:hover{transform:translateY(-2px);box-shadow:0 18px 50px -14px color-mix(in srgb,var(--mmb-info) 45%,transparent)}
  #mmb-launch.mmb-hide{opacity:0;pointer-events:none;transform:translateY(8px)}
  .mmb-orb{width:38px;height:38px;border-radius:50%;flex:none;display:grid;place-items:center;position:relative;
    background:radial-gradient(circle at 32% 28%,color-mix(in srgb,#a78bfa 92%,#fff),#416aec 60%,#0b1030 100%);
    box-shadow:inset 0 1px 3px color-mix(in srgb,#fff 45%,transparent),0 0 18px -2px color-mix(in srgb,#5b7bf0 80%,transparent);
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
  @media(prefers-reduced-motion:reduce){.mmb-orb,.mmb-orb::after,.mmb-tool::before,
    #mmb-panel.max .mmb-rail,#mmb-panel.max .mmb-threads{animation:none}
    #mmb-panel{transition:opacity .18s ease!important}}
  #mmb-launch .ll{font:650 13.5px/1 var(--mmb-font);color:var(--mmb-text)}
  #mmb-launch .lk{font:600 11px/1 var(--mmb-font);color:var(--mmb-muted);margin-top:3px}
  #mmb-launch .lt{display:flex;flex-direction:column}
  /* scrim + panel */
  /* Backdrop deepens as you enter focus mode: a light veil behind the compact chatbox,
     full dim behind the expanded overlay. */
  #mmb-scrim{position:fixed;inset:0;z-index:2147483001;background:#05070c;
    -webkit-backdrop-filter:blur(2px);backdrop-filter:blur(2px);opacity:0;pointer-events:none;
    transition:opacity .5s cubic-bezier(.22,1,.36,1),backdrop-filter .5s ease,-webkit-backdrop-filter .5s ease}
  #mmb-scrim.open{opacity:.34;pointer-events:auto}
  #mmb-scrim.open.max{opacity:.62;-webkit-backdrop-filter:blur(5px);backdrop-filter:blur(5px)}
  #mmb-panel{position:fixed;z-index:2147483002;display:flex;flex-direction:column;overflow:hidden;font-family:var(--mmb-font);color:var(--mmb-text);
    right:18px;bottom:18px;width:min(440px,calc(100vw - 36px));height:min(720px,calc(100vh - 96px));
    border-radius:22px;border:1px solid var(--mmb-line);background:color-mix(in srgb,var(--mmb-panel) 82%,transparent);
    -webkit-backdrop-filter:blur(26px) saturate(1.15);backdrop-filter:blur(26px) saturate(1.15);
    box-shadow:0 40px 100px -30px rgba(0,0,0,.75),inset 0 1px 0 color-mix(in srgb,#fff 6%,transparent);
    transform:translateY(16px) scale(.98);opacity:0;pointer-events:none;transform-origin:bottom right;
    /* CSS owns OPACITY only. TRANSFORM is driven entirely by the Web Animations API (entry
       + the compact↔max morph) so nothing ever transitions transform in CSS — a CSS transform
       transition would fight the WAAPI morph and freeze it at the inverted start. */
    transition:opacity .26s ease}
  #mmb-panel.mmb-top{right:18px;top:64px;bottom:auto;transform-origin:top right;transform:translateY(-16px) scale(.98)}
  #mmb-panel.open{transform:none;opacity:1;pointer-events:auto}
  /* Transform-free centering (inset:0 + margin:auto) so the panel's resting transform is
     'none' in BOTH states — the FLIP invert composes cleanly against it. */
  #mmb-panel.max{inset:0;margin:auto;width:min(1480px,90vw);height:min(1240px,95vh)}
  .mmb-body{display:flex;flex:1;min-height:0}
  .mmb-rail{width:52px;flex:none;display:flex;flex-direction:column;align-items:center;gap:6px;padding:14px 0;border-right:1px solid color-mix(in srgb,var(--mmb-line) 55%,transparent)}
  .mmb-rail .logo{width:30px;height:30px;border-radius:9px;background:linear-gradient(145deg,#5b7bf0,#8b5cf6);display:grid;place-items:center;margin-bottom:8px}
  .mmb-rail .logo svg{width:16px;height:16px;fill:#fff}
  .mmb-icon{width:34px;height:34px;border:none;background:transparent;border-radius:10px;color:var(--mmb-muted);cursor:pointer;display:grid;place-items:center;transition:background .13s,color .13s}
  .mmb-icon:hover{background:color-mix(in srgb,#fff 7%,transparent);color:var(--mmb-text)}
  .mmb-icon svg{width:18px;height:18px;stroke:currentColor;fill:none;stroke-width:1.8}
  .mmb-rail .sp{flex:1}
  .mmb-threads{width:0;flex:none;overflow:hidden auto;border-right:1px solid color-mix(in srgb,var(--mmb-line) 55%,transparent);transition:width .26s ease}
  #mmb-panel.max .mmb-threads{width:236px}
  .mmb-th-h{display:flex;align-items:center;justify-content:space-between;padding:16px 16px 10px}
  .mmb-th-h span{font:700 11px/1 var(--mmb-font);letter-spacing:.08em;text-transform:uppercase;color:var(--mmb-muted)}
  .mmb-search{display:none;align-items:center;gap:8px;margin:2px 10px 8px;padding:7px 10px;border-radius:10px;background:color-mix(in srgb,#fff 5%,transparent);border:1px solid var(--mmb-line)}
  .mmb-search.on{display:flex}
  .mmb-search>svg{width:15px;height:15px;stroke:var(--mmb-muted);fill:none;stroke-width:1.8;flex:none}
  .mmb-search input{flex:1;min-width:0;border:none;background:none;outline:none;color:var(--mmb-text);font:13px/1.2 var(--mmb-font)}
  .mmb-search input::placeholder{color:var(--mmb-muted)}
  .mmb-search .x{border:none;background:none;cursor:pointer;color:var(--mmb-muted);display:grid;place-items:center;padding:2px;border-radius:6px;flex:none;transition:color .12s,opacity .12s}
  .mmb-search .x:hover{color:var(--mmb-text)}
  .mmb-search .x svg{width:13px;height:13px;stroke:currentColor;fill:none;stroke-width:2}
  .mmb-search input:placeholder-shown~.x{opacity:0;pointer-events:none}
  .mmb-ti{margin:2px 8px;padding:9px 11px;border-radius:10px;cursor:pointer;border:1px solid transparent;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .mmb-ti:hover{background:color-mix(in srgb,#fff 6%,transparent)}
  .mmb-ti.on{background:color-mix(in srgb,var(--mmb-info) 14%,transparent);border-color:color-mix(in srgb,var(--mmb-info) 30%,transparent)}
  .mmb-ti .tt{font:600 13px/1.3 var(--mmb-font);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .mmb-ti .tm{font:500 11px/1 var(--mmb-font);color:var(--mmb-muted);margin-top:3px;text-transform:capitalize}
  .mmb-th-empty{color:var(--mmb-muted);font:400 12.5px/1.5 var(--mmb-font);padding:14px 16px}
  .mmb-main{flex:1;display:flex;flex-direction:column;min-width:0}
  .mmb-head{display:flex;align-items:center;gap:8px;padding:14px 14px;flex:none;border-bottom:1px solid color-mix(in srgb,var(--mmb-line) 45%,transparent)}
  .mmb-head .ttl{font:650 14px/1 var(--mmb-font);display:flex;align-items:center;gap:8px}
  .mmb-head .dot{width:7px;height:7px;border-radius:50%;background:#3da564;box-shadow:0 0 8px #3da564}
  .mmb-head .sp{flex:1}
  .mmb-rpill{display:inline-flex;align-items:center;gap:6px;font:600 11.5px/1 var(--mmb-font);cursor:pointer;
    color:color-mix(in srgb,var(--mmb-violet) 84%,#fff);background:color-mix(in srgb,var(--mmb-violet) 12%,transparent);
    border:1px solid color-mix(in srgb,var(--mmb-violet) 30%,transparent);border-radius:999px;padding:6px 11px}
  .mmb-rpill.on{background:linear-gradient(180deg,color-mix(in srgb,#a78bfa 90%,#fff),var(--mmb-violet));color:#fff;border-color:transparent}
  .mmb-rpill.mmb-off{display:none}
  #mmb-panel.max .mmb-menu,#mmb-panel.max .mmb-sidescrim{display:none}
  #mmb-panel:not(.max) .mmb-rail{display:none}
  #mmb-panel:not(.max) .mmb-threads{position:absolute;left:0;top:0;bottom:0;width:236px;z-index:6;display:block;
    background:color-mix(in srgb,var(--mmb-panel) 94%,transparent);-webkit-backdrop-filter:blur(22px);backdrop-filter:blur(22px);
    border-right:1px solid var(--mmb-line);transform:translateX(-101%);transition:transform .26s cubic-bezier(.2,.8,.2,1)}
  #mmb-panel:not(.max).show-side .mmb-threads{transform:none;box-shadow:10px 0 40px -12px rgba(0,0,0,.6)}
  #mmb-panel:not(.max) .mmb-sidescrim{position:absolute;inset:0;z-index:5;background:rgba(0,0,0,.32);opacity:0;pointer-events:none;transition:opacity .2s ease}
  #mmb-panel:not(.max).show-side .mmb-sidescrim{opacity:1;pointer-events:auto}
  .mmb-scroll{flex:1;overflow-y:auto;padding:20px clamp(18px,6%,64px);display:flex;flex-direction:column;gap:15px}
  #mmb-panel.max .mmb-scroll{padding:26px clamp(24px,10%,120px)}
  .mmb-empty{flex:1;display:flex;flex-direction:column;justify-content:center}
  .mmb-hero h1{margin:0;font:800 clamp(22px,3vw,38px)/1.1 var(--mmb-font);letter-spacing:-.02em}
  #mmb-panel:not(.max) .mmb-hero h1{font-size:22px}
  .mmb-hero .g1{background:linear-gradient(90deg,#c7d0e0,#8b93a1);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
  .mmb-hero .nm{background:linear-gradient(90deg,#8b5cf6,#5b7bf0);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
  .mmb-hero .g2{background:linear-gradient(90deg,#e6eaf0 30%,#8b5cf6);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
  .mmb-hero p{margin:11px 0 0;color:var(--mmb-muted);font:400 14px/1.5 var(--mmb-font);max-width:460px}
  #mmb-panel:not(.max) .mmb-hero p{font-size:13px}
  .mmb-cards{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-top:20px;max-width:620px}
  #mmb-panel.max .mmb-cards{grid-template-columns:repeat(4,1fr);max-width:920px}
  #mmb-panel:not(.max) .mmb-cards{grid-template-columns:1fr;gap:8px}
  .mmb-cardp{text-align:left;cursor:pointer;font-family:var(--mmb-font);color:var(--mmb-text);
    background:color-mix(in srgb,var(--mmb-panel) 50%,transparent);border:1px solid var(--mmb-line);
    -webkit-backdrop-filter:blur(10px);backdrop-filter:blur(10px);border-radius:15px;padding:14px;min-height:104px;
    display:flex;flex-direction:column;justify-content:space-between;gap:10px;transition:transform .14s,border-color .14s,background .14s}
  #mmb-panel:not(.max) .mmb-cardp{min-height:0;flex-direction:row;align-items:center;padding:12px 13px}
  .mmb-cardp:hover{transform:translateY(-2px);border-color:color-mix(in srgb,var(--mmb-info) 42%,transparent);
    background:color-mix(in srgb,var(--mmb-info) 9%,color-mix(in srgb,var(--mmb-panel) 50%,transparent))}
  .mmb-cardp .cp{font:500 12.5px/1.35 var(--mmb-font);color:color-mix(in srgb,var(--mmb-text) 88%,var(--mmb-muted))}
  .mmb-cardp .ci{width:26px;height:26px;flex:none;border-radius:8px;display:grid;place-items:center;color:var(--mmb-info);background:color-mix(in srgb,var(--mmb-info) 12%,transparent)}
  .mmb-cardp .ci svg{width:15px;height:15px;stroke:currentColor;fill:none;stroke-width:1.8}
  /* messages */
  .mmb-msg{display:flex;flex-direction:column;gap:4px;max-width:88%}
  .mmb-msg.user{align-self:flex-end;align-items:flex-end}
  .mmb-msg.assistant{align-self:flex-start;align-items:flex-start;max-width:100%}
  .mmb-bub{padding:12px 15px;border-radius:16px;font:14.5px/1.62 var(--mmb-font);word-break:break-word}
  .mmb-msg.user .mmb-bub{background:linear-gradient(180deg,color-mix(in srgb,var(--mmb-info) 92%,#fff),var(--mmb-info));color:#fff;border-bottom-right-radius:5px;box-shadow:0 8px 22px -10px color-mix(in srgb,var(--mmb-info) 70%,transparent)}
  .mmb-msg.assistant .mmb-bub{background:color-mix(in srgb,var(--mmb-panel) 60%,transparent);border:1px solid color-mix(in srgb,#fff 9%,transparent);-webkit-backdrop-filter:blur(12px);backdrop-filter:blur(12px);border-bottom-left-radius:5px;box-shadow:0 10px 30px -18px rgba(0,0,0,.5)}
  .mmb-bub p{margin:0 0 9px}.mmb-bub p:last-child{margin-bottom:0}
  .mmb-bub ul,.mmb-bub ol{margin:7px 0 9px 20px;padding:0}.mmb-bub li{margin:4px 0}
  .mmb-bub strong{font-weight:700;color:color-mix(in srgb,var(--mmb-text) 92%,#fff)}
  .mmb-bub .mmb-chart{margin:10px 0 2px;border-radius:12px;overflow:hidden;border:1px solid color-mix(in srgb,#fff 8%,transparent);background:#0E1420}
  .mmb-bub .mmb-chart svg{display:block;width:100%;height:auto}
  .mmb-txt:empty,.mmb-charts:empty{display:none}
  @media print{#mmb-root{display:none!important}}
  .mmb-tool{font:12px/1.3 var(--mmb-font);color:var(--mmb-muted);display:flex;align-items:center;gap:7px;padding:1px 4px}
  .mmb-tool::before{content:'';width:7px;height:7px;border-radius:50%;background:var(--mmb-info);box-shadow:0 0 8px var(--mmb-info);animation:mmb-pulse 1.4s ease-in-out infinite}
  @keyframes mmb-pulse{0%,100%{opacity:.4;transform:scale(.85)}50%{opacity:1;transform:scale(1.1)}}
  .mmb-cites{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
  .mmb-cite{font:11px/1.3 var(--mmb-font);background:color-mix(in srgb,var(--mmb-info) 11%,transparent);border:1px solid color-mix(in srgb,var(--mmb-info) 26%,transparent);border-radius:999px;padding:3px 10px;color:color-mix(in srgb,var(--mmb-info) 86%,var(--mmb-text));text-decoration:none;cursor:pointer}
  .mmb-cite:hover{background:color-mix(in srgb,var(--mmb-info) 20%,transparent)}
  .mmb-typing{display:inline-flex;gap:4px;padding:6px 3px}
  .mmb-typing span{width:7px;height:7px;border-radius:50%;background:var(--mmb-info);opacity:.6;animation:mmb-bounce 1.3s ease-in-out infinite}
  .mmb-typing span:nth-child(2){animation-delay:.18s}.mmb-typing span:nth-child(3){animation-delay:.36s}
  @keyframes mmb-bounce{0%,60%,100%{transform:translateY(0);opacity:.5}30%{transform:translateY(-6px);opacity:1}}
  .mmb-meta{font:11px/1.4 var(--mmb-font);color:var(--mmb-muted);padding:0 4px}
  .mmb-upgrade{display:none;margin:0 0 12px;padding:13px 15px;border-radius:13px;font:13px/1.5 var(--mmb-font);
    background:color-mix(in srgb,#e0a030 12%,color-mix(in srgb,var(--mmb-panel) 55%,transparent));border:1px solid color-mix(in srgb,#e0a030 34%,transparent)}
  .mmb-upgrade a{color:var(--mmb-info);font-weight:700;text-decoration:underline}
  /* composer */
  .mmb-comp{flex:none;padding:14px clamp(18px,6%,64px) 14px}
  #mmb-panel.max .mmb-comp{padding:14px clamp(24px,10%,120px) 16px}
  .mmb-box{border-radius:18px;border:1px solid var(--mmb-line);background:color-mix(in srgb,var(--mmb-panel2) 60%,transparent);
    -webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px);box-shadow:0 14px 40px -18px rgba(0,0,0,.6);overflow:hidden}
  .mmb-ctx{display:none;align-items:center;gap:7px;padding:9px 12px 0}
  .mmb-ctx.on{display:flex}
  .mmb-ctx .chip{display:inline-flex;align-items:center;gap:6px;white-space:nowrap;font:600 11.5px/1 var(--mmb-font);
    color:color-mix(in srgb,var(--mmb-info) 92%,#fff);background:color-mix(in srgb,var(--mmb-info) 13%,transparent);
    border:1px solid color-mix(in srgb,var(--mmb-info) 30%,transparent);border-radius:999px;padding:4px 11px 4px 8px}
  .mmb-ctx .chip .cx{width:13px;height:13px;flex:none;stroke:currentColor;fill:none;stroke-width:1.6;opacity:.9;animation:mmb-breathe 4.6s ease-in-out infinite}
  .mmb-ctx .chip b{font:700 11.5px/1 var(--mmb-font);letter-spacing:.03em;color:var(--mmb-text)}
  .mmb-thumbs{display:none;flex-wrap:wrap;gap:8px;padding:10px 12px 0}
  .mmb-thumbs.on{display:flex}
  .mmb-thumb{position:relative;width:52px;height:52px;border-radius:10px;overflow:hidden;border:1px solid var(--mmb-line);background:#0b0e14;flex:none}
  .mmb-thumb img{width:100%;height:100%;object-fit:cover;display:block}
  .mmb-thumb .x{position:absolute;top:2px;right:2px;width:16px;height:16px;border:none;border-radius:50%;cursor:pointer;display:grid;place-items:center;
    background:rgba(8,10,16,.82);color:#fff;font:700 11px/1 var(--mmb-font);padding:0}
  .mmb-thumb .x:hover{background:#e05555}
  /* attached-image thumbs inside a sent user bubble */
  .mmb-bub .mmb-imgs{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px}
  .mmb-bub .mmb-imgs img{width:120px;max-width:44vw;height:auto;border-radius:10px;border:1px solid color-mix(in srgb,#fff 18%,transparent);display:block}
  .mmb-ta{width:100%;border:none;background:none;outline:none;resize:none;color:var(--mmb-text);font:15px/1.5 var(--mmb-font);padding:12px 14px 6px;min-height:26px;max-height:150px}
  .mmb-ta::placeholder{color:color-mix(in srgb,var(--mmb-muted) 92%,transparent)}
  .mmb-tools{display:flex;align-items:center;gap:8px;padding:6px 10px 10px}
  .mmb-tools .sp{flex:1}
  .mmb-seg{display:flex;gap:2px;padding:2px;border-radius:999px;background:color-mix(in srgb,#fff 5%,transparent);border:1px solid var(--mmb-line)}
  .mmb-seg button{border:none;background:transparent;color:var(--mmb-muted);font:600 11.5px/1 var(--mmb-font);padding:5px 11px;border-radius:999px;cursor:pointer}
  .mmb-seg button.on{background:linear-gradient(180deg,color-mix(in srgb,var(--mmb-info) 92%,#fff),var(--mmb-info));color:#fff;box-shadow:0 2px 10px -3px color-mix(in srgb,var(--mmb-info) 70%,transparent)}
  .mmb-q{font:600 11px/1 var(--mmb-font);color:var(--mmb-muted);padding:0 2px}
  .mmb-q.warn{color:#e0a030}.mmb-q.empty{color:#e05555}
  .mmb-tbtn{width:34px;height:34px;border:none;background:transparent;border-radius:10px;color:var(--mmb-muted);cursor:pointer;display:grid;place-items:center}
  .mmb-tbtn:hover{background:color-mix(in srgb,#fff 7%,transparent);color:var(--mmb-text)}
  .mmb-tbtn svg{width:18px;height:18px;stroke:currentColor;fill:none;stroke-width:1.8}
  .mmb-send{width:36px;height:36px;border:none;border-radius:12px;cursor:pointer;display:grid;place-items:center;color:#fff;
    background:linear-gradient(180deg,color-mix(in srgb,var(--mmb-info) 92%,#fff),var(--mmb-info));box-shadow:0 6px 18px -6px color-mix(in srgb,var(--mmb-info) 75%,transparent)}
  .mmb-send:disabled{opacity:.4;cursor:not-allowed;box-shadow:none}
  .mmb-send svg{width:17px;height:17px;stroke:currentColor;fill:none;stroke-width:2}
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
    #mmb-panel.max .mmb-rail,#mmb-panel.max .mmb-threads{display:none}}
  /* follow-up suggestion chips (rendered under the latest reply) */
  .mmb-sugg{display:flex;flex-direction:column;align-items:flex-start;gap:6px;margin-top:8px}
  .mmb-sug{font:12.5px/1.35 var(--mmb-font);color:color-mix(in srgb,var(--mmb-text) 78%,var(--mmb-muted));background:color-mix(in srgb,#fff 4%,transparent);border:1px solid var(--mmb-line);border-radius:12px;padding:7px 12px;text-align:left;cursor:pointer;max-width:100%;transition:border-color .13s,background .13s,color .13s}
  .mmb-sug:hover{border-color:color-mix(in srgb,var(--mmb-info) 40%,transparent);background:color-mix(in srgb,var(--mmb-info) 8%,transparent);color:var(--mmb-text)}
  .mmb-sug .g{color:var(--mmb-muted);margin-right:6px}
  /* copy-answer affordance (top-right of each assistant bubble) */
  .mmb-msg.assistant .mmb-bub{position:relative}
  .mmb-copy{position:absolute;top:6px;right:6px;width:24px;height:24px;border:none;background:transparent;border-radius:7px;color:var(--mmb-muted);cursor:pointer;display:grid;place-items:center;opacity:0;pointer-events:none;transition:opacity .13s,color .13s,background .13s}
  .mmb-bub:hover .mmb-copy{opacity:.85;pointer-events:auto}
  .mmb-copy:hover{opacity:1;color:var(--mmb-text);background:color-mix(in srgb,#fff 7%,transparent)}
  .mmb-copy svg{width:14px;height:14px;stroke:currentColor;fill:none;stroke-width:1.8}
  /* "explain this panel" hover affordance on dashboard island cards */
  .mmb-exp{position:absolute;top:10px;right:10px;width:26px;height:26px;border-radius:50%;cursor:pointer;padding:0;
    background:color-mix(in srgb,var(--mmb-panel) 72%,transparent);-webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px);
    border:1px solid var(--mmb-line);display:grid;place-items:center;opacity:0;pointer-events:none;transition:opacity .15s,border-color .15s,box-shadow .15s;z-index:5}
  .mmb-exp svg{width:12px;height:12px;fill:#fff;opacity:.9}
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

  /* ── DOM ─────────────────────────────────────────────────────────────── */
  var root = DOC.createElement('div');
  root.id = 'mmb-root';
  var st = DOC.createElement('style'); st.textContent = CSS; root.appendChild(st);

  var launchHtml = ANCHOR === 'br' ? (
    '<div id="mmb-launch"><div class="mmb-orb">' + ORB + '</div>' +
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
          '<button class="mmb-rpill mmb-off" data-act="research">' + ic('<path d="M12 3v3M12 18v3M3 12h3M18 12h3M6 6l2 2M16 16l2 2M18 6l-2 2M8 16l-2 2"/>') + LB('Deep Research', '深度研究') + '</button>' +
          '<div class="sp"></div>' +
          '<button class="mmb-icon" data-act="max" title="Expand">' + ic('<path d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5"/>') + '</button>' +
          '<button class="mmb-icon" data-act="new" title="New chat">' + ic('<path d="M12 5v14M5 12h14"/>') + '</button>' +
          '<button class="mmb-icon" data-act="close" title="Close">' + ic('<path d="M6 6l12 12M18 6L6 18"/>') + '</button>' +
        '</div>' +
        '<div class="mmb-scroll" id="mmb-scroll" role="log" aria-label="' + L('Conversation', '对话') + '" tabindex="0"></div>' +
        '<div id="mmb-live" class="mmb-sr" aria-live="polite" role="status"></div>' +
        '<div class="mmb-comp"><div class="mmb-upgrade" id="mmb-upgrade"></div>' +
          '<div class="mmb-box"><div class="mmb-ctx" id="mmb-ctx"></div>' +
            '<div class="mmb-thumbs" id="mmb-thumbs"></div>' +
            '<textarea class="mmb-ta" id="mmb-ta" rows="1" maxlength="2000" data-ph-en="Ask about any dashboard, signal, or ticker…" data-ph-zh="询问任意看板、信号或标的…" placeholder="' + L('Ask about any dashboard, signal, or ticker…', '询问任意看板、信号或标的…') + '"></textarea>' +
            '<input type="file" id="mmb-file" accept="image/png,image/jpeg,image/webp,image/gif" multiple hidden>' +
            '<div class="mmb-tools">' +
              '<div class="mmb-seg" id="mmb-lane"><button data-lane="fast" class="on">⚡ ' + LB('Fast', '快速') + '</button><button data-lane="pro">◈ Pro</button></div>' +
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
      searchWrap = $('#mmb-search'), searchIn = $('#mmb-search-in');

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
  /* Split raw markdown into block strings on blank lines, respecting ``` fences.
     A fenced block stays whole even across blanks. Returns array of block texts. */
  function mdSplit(text) {
    var lines = String(text || '').split('\n'), blocks = [], cur = [], inFence = false;
    function push() { if (cur.length) { blocks.push(cur.join('\n')); cur = []; } }
    for (var i = 0; i < lines.length; i++) {
      var ln = lines[i];
      if (/^```/.test(ln)) {
        if (!inFence) { push(); inFence = true; cur.push(ln); }
        else { cur.push(ln); push(); inFence = false; }
        continue;
      }
      if (inFence) { cur.push(ln); continue; }
      if (!ln.trim()) { push(); }
      else cur.push(ln);
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
        var finish = function () {
          renderMdInto(container, raw);
          revealed = raw; committedLen = raw.length; pending = ''; openText = null;
          if (caret) { caret.parentNode && caret.parentNode.removeChild(caret); caret = null; }
          if (cb) cb();
        };
        if (reduced || !pending.length) { revealed += pending; pending = ''; finish(); return; }
        doneFlush = true; onDrained = finish; schedule();
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
        if (!proEligible && researchMode) setResearch(false);
        renderQuota();
      }).catch(function () { if (!authed) enterGuest(false); });
  }
  function renderQuota() {
    var q = quotas[researchMode ? 'pro' : lane];
    if (!q) { qEl.textContent = ''; qEl.removeAttribute('title'); return; }
    var pre = (researchMode || lane === 'pro') ? '◈ ' : '⚡ ';
    /* title is English-only per house law (no translated text in title= attrs). */
    if (q.limit < 0) { qEl.textContent = pre + '∞'; qEl.className = 'mmb-q'; qEl.setAttribute('title', 'Unlimited'); return; }  /* unlimited */
    qEl.textContent = pre + q.remaining + '/' + q.limit;
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
  function buildThreadItem(t) {
    var d = DOC.createElement('div'); d.className = 'mmb-ti' + (t.id === threadId ? ' on' : ''); d.dataset.id = t.id;
    var date = ''; try { date = new Date(t.updated_at).toLocaleDateString(); } catch (e) {}
    d.innerHTML = '<div class="tt">' + esc(t.title || L('Untitled', '未命名')) + '</div><div class="tm">' + esc(t.lane || 'fast') + ' · ' + esc(date) + '</div>';
    d.addEventListener('click', function () { openThread(t.id); if (!panel.classList.contains('max')) panel.classList.remove('show-side'); });
    return d;
  }
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
  function openThread(id) {
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
      root.querySelector('.mmb-main').appendChild(jumpPill);
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
    var cards = PROMPTS.map(function (p) {
      var paths = p[0].split('|').map(function (d) { return '<path d="' + d + '"/>'; }).join('');
      var txt = L(p[1], p[2]);
      return '<button class="mmb-cardp" data-p="' + esc(txt) + '"><div class="ci"><svg viewBox="0 0 24 24">' + paths + '</svg></div><span class="cp">' + esc(txt) + '</span></button>';
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
    if ($('#mmb-emptystate')) renderEmpty();
    paintThreads();   /* self-routes to the guest sign-in prompt when in guest mode */
    renderQuota();     /* refresh the meter's title in the new language sense */
  }

  /* ── send (SSE) ──────────────────────────────────────────────────────────────
     send() builds a payload from the live composer + attaches the user bubble, then
     hands off to runStream(). runStream() is payload-only so Regenerate and Retry can
     replay the exact same turn (text + images + lane + thread) with no backend change. */
  var lastTurn = null;   // { text, imgs, lane, mode } — last user turn, for regenerate
  function send(text) {
    text = (text || ta.value).trim();
    var imgs = pendingImages.slice();
    if ((!text && !imgs.length) || streaming) return;
    /* Guests may send (Fast lane) without the sign-in modal; only fully-gated (non-guest,
       signed-out) sessions are bounced to sign-in. */
    if (!authed && !guestMode && window.MDXAuth && window.MDXAuth.enabled && window.MDXAuth.enabled()) { window.MDXAuth.open('signin'); return; }
    var ctx = { page: (ANCHOR === 'top' ? 'terminal' : 'dashboard') }; if (ctxSymbol) ctx.symbol = ctxSymbol;
    /* an "explain this panel" request carries the panel key once, then clears */
    if (explainPanel) { ctx.panel = explainPanel; explainPanel = null; }
    var payload = { text: text, imgs: imgs, lane: researchMode ? 'pro' : lane, mode: researchMode ? 'research' : 'chat', ctx: ctx };
    lastTurn = { text: text, imgs: imgs, lane: payload.lane, mode: payload.mode };
    pendingImages = []; renderThumbs();
    ta.value = ''; autosize(); clearDraft(); syncSend();
    pinned = true; hideJump();
    runStream(payload, true);
  }
  /* Replay the last user turn on the same thread/lane (client resend, no backend change). */
  function regenerate() {
    if (streaming || !lastTurn) return;
    runStream({ text: lastTurn.text, imgs: (lastTurn.imgs || []).slice(), lane: lastTurn.lane, mode: lastTurn.mode,
                ctx: (function () { var c = { page: (ANCHOR === 'top' ? 'terminal' : 'dashboard') }; if (ctxSymbol) c.symbol = ctxSymbol; return c; })() }, false);
  }
  /* runStream(payload, showUser): runs one SSE turn. showUser=false skips drawing a new
     user bubble (used by regenerate — the user turn is already on screen). */
  function runStream(payload, showUser) {
    /* only the latest reply carries follow-up chips — clear any stale rows */
    root.querySelectorAll('.mmb-sugg').forEach(function (n) { n.remove(); });
    if (showUser) {
      var ub = appendMsg('user', payload.text);
      if (payload.imgs && payload.imgs.length) {
        var iw = el('div', 'mmb-imgs');
        payload.imgs.forEach(function (s) { var im = el('img'); im.src = s; im.alt = ''; im.addEventListener('load', stickAfter); iw.appendChild(im); });
        ub.insertBefore(iw, ub.firstChild);
      }
    }
    sendBtn.disabled = true; streaming = true; upgradeEl.style.display = 'none';
    setBusy(true);
    var typing = el('div', 'mmb-msg assistant');
    typing.innerHTML = '<div class="mmb-bub"><span class="mmb-orbmark"><svg viewBox="0 0 24 24"><path d="' + ORB_PATH + '"/></svg></span><span class="mmb-typing"><span></span><span></span><span></span></span></div>';
    scroll.appendChild(typing); stick();
    var bub = null, stream = null, steps = null, suggestions = null, sawDelta = false;
    var apiText = payload.text || L('Please analyze the attached image.', '请分析所附图片。');
    var body = JSON.stringify({ message: apiText, lane: payload.lane, mode: payload.mode, thread_id: threadId || undefined, context: payload.ctx, images: (payload.imgs && payload.imgs.length) ? payload.imgs : undefined });
    if (streamAbort) { try { streamAbort.abort(); } catch (e) {} }
    var ac = (typeof AbortController !== 'undefined') ? new AbortController() : null; streamAbort = ac;
    function ensureBub() { if (!bub) { if (typing.parentNode) typing.remove(); bub = appendMsg('assistant', ''); stream = MdStream(bubTxt(bub)); stream.startCaret(); markLastAssistant(); } return bub; }
    function endStream() { streaming = false; streamAbort = null; setBusy(false); syncSend(); }
    withAuth({ 'Content-Type': 'application/json' }).then(function (h) {
      return fetch(API + '/api/brain/stream', { method: 'POST', headers: h, credentials: 'include', body: body, signal: ac ? ac.signal : undefined });
    }).then(function (res) {
      if (res.status === 401) { if (typing.parentNode) typing.remove(); endStream(); if (window.MDXAuth && window.MDXAuth.enabled()) window.MDXAuth.open('signin'); else if (CFG.onAuthRequired) { try { CFG.onAuthRequired(); } catch (e) {} } return; }
      if (res.status === 402) { if (typing.parentNode) typing.remove(); endStream(); return res.json().then(showUpgrade).catch(function () { showUpgrade({}); }); }
      if (!res.ok || !res.body) { if (typing.parentNode) typing.remove(); endStream(); errorCard(payload, ''); return; }
      var reader = res.body.getReader(), dec = new TextDecoder(), buf = '';
      function pump() {
        return reader.read().then(function (r) {
          if (r.done) { finish(); return; }
          buf += dec.decode(r.value, { stream: true }); var lines = buf.split('\n'); buf = lines.pop() || '';
          lines.forEach(function (ln) {
            ln = ln.trim(); if (ln.indexOf('data:') !== 0) return; var data = ln.slice(5).trim(); if (!data) return;
            var j; try { j = JSON.parse(data); } catch (e) { return; }
            if (j.type === 'meta') { if (j.thread_id) threadId = j.thread_id; if (j.quota) { quotas[j.quota.lane] = j.quota; renderQuota(); } }
            else if (j.type === 'tool') { ensureBub(); if (!steps) { steps = el('div', 'mmb-tool'); steps.textContent = L('Reading ', '正在读取 ') + (j.name || '') + '…'; bub.insertBefore(steps, bubTxt(bub)); } else steps.textContent = L('Reading ', '正在读取 ') + (j.name || '') + '…'; stickAfter(); }
            else if (j.type === 'chart' && j.svg) { ensureBub(); var cw = el('div', 'mmb-chart'); cw.innerHTML = j.svg; (bub.querySelector('.mmb-charts') || bub).appendChild(cw); stickAfter(); }
            else if (j.type === 'delta') { ensureBub(); if (steps) { steps.remove(); steps = null; } sawDelta = true; bub._raw = (bub._raw || '') + j.text; stream.push(j.text); }
            else if (j.type === 'suggest') { if (j.items && j.items.length) suggestions = j.items.slice(0, 3); }
            /* host bridges (Terminal): chart-command + annotate events are executed by the
               host page, not the widget — forward them to the CFG callbacks when provided. */
            else if (j.type === 'command') { try { if (CFG.onCommand) CFG.onCommand(j); } catch (e) {} }
            else if (j.type === 'annotate') { try { if (CFG.onAnnotate) CFG.onAnnotate(j); } catch (e) {} }
            else if (j.type === 'done') { finalizeDone(j); }
            else if (j.type === 'error') {
              if (!sawDelta && !(bub && bub._raw)) { if (typing.parentNode) typing.remove(); endStream(); errorCard(payload, j.message || ''); }
              else { ensureBub(); bub._raw = (bub._raw || '') + '\n\n_' + (j.message || 'error') + '_'; stream.push('\n\n_' + (j.message || 'error') + '_'); }
            }
          });
          return pump();
        });
      }
      function finalizeDone(j) {
        ensureBub(); if (steps) { steps.remove(); steps = null; }
        stream.finalize(function () {
          if (j && j.citations && j.citations.length) addCites(bub, j.citations);
          if (suggestions && suggestions.length) addSuggest(bub, suggestions);
          bumpTime(bub); stickAfter();
        });
        if (j && j.quota) { quotas[j.quota.lane] = j.quota; renderQuota(); }
      }
      function finish() {
        if (bub && stream) { stream.finalize(function () { bumpTime(bub); stickAfter(); }); }
        else if (!bub) { if (typing.parentNode) typing.remove(); errorCard(payload, ''); }
        endStream(); loadThreads(); announceDone();
      }
      return pump();
    }).catch(function (err) {
      /* AbortError = user pressed Stop; keep partial, no error card. */
      var aborted = err && (err.name === 'AbortError');
      if (aborted) { endStream(); return; }
      if (typing.parentNode) typing.remove();
      if (bub && stream && (sawDelta || bub._raw)) { stream.finalize(function () { bumpTime(bub); stickAfter(); }); }
      else { errorCard(payload, ''); }
      endStream();
    });
    /* expose the live stream to stopStream() so the Stop button can finalize the partial */
    activeStream = { get bub() { return bub; }, get stream() { return stream; }, get typing() { return typing; }, payload: payload };
  }
  var activeStream = null;
  /* Stop: abort the reader, keep partial text, append a muted "· stopped" tag, finalize. */
  function stopStream() {
    if (!streaming) return;
    if (streamAbort) { try { streamAbort.abort(); } catch (e) {} }
    var a = activeStream;
    if (a && a.stream && a.bub) {
      a.stream.stop();
      var txt = a.bub.querySelector('.mmb-txt') || a.bub;
      var s = el('span', 'mmb-stopped'); s.textContent = L(' · stopped', ' · 已停止'); txt.appendChild(s);
      bumpTime(a.bub); markLastAssistant();
    } else if (a && a.typing && a.typing.parentNode) { a.typing.remove(); }
    streaming = false; streamAbort = null; setBusy(false); syncSend(); stickAfter();
  }
  /* Header busy dot + send↔stop button morph. */
  function setBusy(on) {
    var dot = root.querySelector('.mmb-head .dot'); if (dot) dot.classList.toggle('busy', on);
    sendBtn.classList.toggle('mmb-stop', on);
    sendBtn.disabled = on ? false : ((!ta.value.trim() && !pendingImages.length));
    sendBtn.title = on ? 'Stop' : 'Send';
    sendBtn.setAttribute('aria-label', on ? L('Stop', '停止') : L('Send', '发送'));
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
    items.slice(0, 3).forEach(function (q) {
      if (!q) return;
      var btn = DOC.createElement('button'); btn.className = 'mmb-sug';
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

  /* ── toggles ── */
  function setResearch(on) { researchMode = on; researchBtn.classList.toggle('on', on); researchBtn.setAttribute('aria-pressed', on); renderQuota(); }
  function autosize() { ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight, 150) + 'px'; }

  /* ── widget mechanics ── */
  /* Always open COMPACT (operator order): dashboard = corner chatbox, Terminal = top
     drop-down. The expand button offers the large overlay — desktop only. */
  function open() {
    refreshCtx(); scrim.classList.add('open'); panel.classList.add('open');
    if (ANCHOR === 'top') panel.classList.add('mmb-top');
    if (launch) launch.classList.add('mmb-hide');
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
    setTimeout(function () { ta.focus(); }, 260);
  }
  function close() { if (streamAbort) { try { streamAbort.abort(); } catch (e) {} streamAbort = null; streaming = false; } if (panel._morph) { try { panel._morph.cancel(); } catch (e) {} } scrim.classList.remove('open', 'max'); panel.classList.remove('open', 'max', 'show-side'); if (launch) launch.classList.remove('mmb-hide'); }
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
  function newChat() { threadId = null; pendingImages = []; renderThumbs(); root.querySelectorAll('.mmb-ti').forEach(function (el) { el.classList.remove('on'); }); clearMsgs(); ta.value = ''; autosize(); syncSend(); updateCounter(); closeSlash(); restoreDraft(); if (!panel.classList.contains('max')) panel.classList.remove('show-side'); }

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
      lane = t.dataset.lane; root.querySelectorAll('#mmb-lane button').forEach(function (b) { b.classList.toggle('on', b === t); }); renderQuota(); return;
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
  if (searchIn) {
    searchIn.addEventListener('input', paintThreads);
    searchIn.addEventListener('keydown', function (e) { if (e.key === 'Escape') { e.preventDefault(); toggleSearch(false); } });
  }
  /* follow the host's language switch live — dashboard fires 'langchange' on the
     document (theme.js setLang), the Terminal fires 'mm:lang' on window (i18n.tsx). */
  DOC.addEventListener('langchange', relabel);
  window.addEventListener('mm:lang', relabel);
  if (launch) launch.addEventListener('click', open);
  scrim.addEventListener('click', close);
  /* Send button doubles as Stop mid-stream (the arrow morphs to a square). */
  sendBtn.addEventListener('click', function () { if (streaming) stopStream(); else send(); });
  ta.addEventListener('input', function () { autosize(); syncSend(); updateCounter(); slashSync(); saveDraft(); });
  ta.addEventListener('keydown', function (e) {
    if (slashKeydown(e)) return;                             // palette owns ↑/↓/Enter/Esc while open
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); send(); return; }   // Cmd/Ctrl+Enter always sends
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
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
      var d = DOC.createElement('div'); d.className = 'mmb-thumb';
      /* set src via the DOM property (never interpolate a data URI into innerHTML) */
      var im = DOC.createElement('img'); im.src = src; im.alt = '';
      var x = DOC.createElement('button'); x.className = 'x'; x.setAttribute('data-rmimg', i); x.title = 'Remove'; x.textContent = '✕';
      d.appendChild(im); d.appendChild(x); thumbsEl.appendChild(d);
    });
    syncSend();
  }
  /* send is enabled when there's text OR at least one attached image (and not mid-stream) */
  function syncSend() { sendBtn.disabled = (!ta.value.trim() && !pendingImages.length) || streaming; }

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
    var m = /[?&]symbol=([A-Za-z0-9.\-]+)/i.exec(location.search); if (!s && m) s = m[1];
    ctxSymbol = (s || '').toString().toUpperCase().slice(0, 10);
    if (ctxSymbol) { ctxEl.className = 'mmb-ctx on'; ctxEl.innerHTML = '<span class="chip" title="Active symbol"><svg class="cx" viewBox="0 0 24 24"><circle cx="12" cy="12" r="6.5"/><circle cx="12" cy="12" r="1.7" fill="currentColor" stroke="none"/></svg><b>' + esc(ctxSymbol) + '</b></span>'; }
    else ctxEl.className = 'mmb-ctx';
  }
  refreshCtx(); renderEmpty();

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
