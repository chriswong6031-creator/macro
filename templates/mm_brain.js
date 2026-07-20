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
  .mmb-newc{display:inline-flex;align-items:center;gap:5px;font:600 12px/1 var(--mmb-font);color:color-mix(in srgb,var(--mmb-info) 90%,#fff);cursor:pointer;
    background:color-mix(in srgb,var(--mmb-info) 16%,transparent);border:1px solid color-mix(in srgb,var(--mmb-info) 32%,transparent);border-radius:999px;padding:5px 11px}
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
    '<div class="lt"><span class="ll">' + L('Ask Mastermind', '问操盘大脑') + '</span>' +
    '<span class="lk">' + L('Brain · your desk copilot', '大脑 · 你的桌面副驾') + '</span></div></div>') : '';

  root.insertAdjacentHTML('beforeend', launchHtml +
    '<div id="mmb-scrim"></div>' +
    '<div id="mmb-panel"><div class="mmb-body">' +
      '<div class="mmb-rail"><div class="logo">' + ORB + '</div>' +
        '<button class="mmb-icon" data-act="new" title="New chat">' + ic('<path d="M12 5v14M5 12h14"/>') + '</button>' +
        '<button class="mmb-icon" title="Search">' + ic('<circle cx="11" cy="11" r="7"/><path d="M21 21l-4-4"/>') + '</button>' +
        '<button class="mmb-icon" data-act="home" title="Dashboard">' + ic('<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/>') + '</button>' +
        '<div class="sp"></div>' +
      '</div>' +
      '<div class="mmb-threads"><div class="mmb-th-h"><span>' + L('Chats', '对话') + '</span>' +
        '<button class="mmb-newc" data-act="new">' + ic('<path d="M12 5v14M5 12h14"/>') + L('New', '新建') + '</button></div>' +
        '<div id="mmb-tlist"><div class="mmb-th-empty">' + L('Your conversations appear here.', '你的对话会显示在这里。') + '</div></div>' +
      '</div>' +
      '<div class="mmb-main"><div class="mmb-sidescrim" data-act="side"></div>' +
        '<div class="mmb-head">' +
          '<button class="mmb-icon mmb-menu" data-act="side" title="Chats">' + ic('<path d="M4 6h16M4 12h16M4 18h16"/>') + '</button>' +
          '<span class="ttl"><span class="dot"></span>' + L('Mastermind Brain', '操盘大脑') + '</span>' +
          '<button class="mmb-rpill mmb-off" data-act="research">' + ic('<path d="M12 3v3M12 18v3M3 12h3M18 12h3M6 6l2 2M16 16l2 2M18 6l-2 2M8 16l-2 2"/>') + L('Deep Research', '深度研究') + '</button>' +
          '<div class="sp"></div>' +
          '<button class="mmb-icon" data-act="max" title="Expand">' + ic('<path d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5"/>') + '</button>' +
          '<button class="mmb-icon" data-act="new" title="New chat">' + ic('<path d="M12 5v14M5 12h14"/>') + '</button>' +
          '<button class="mmb-icon" data-act="close" title="Close">' + ic('<path d="M6 6l12 12M18 6L6 18"/>') + '</button>' +
        '</div>' +
        '<div class="mmb-scroll" id="mmb-scroll"></div>' +
        '<div class="mmb-comp"><div class="mmb-upgrade" id="mmb-upgrade"></div>' +
          '<div class="mmb-box"><div class="mmb-ctx" id="mmb-ctx"></div>' +
            '<div class="mmb-thumbs" id="mmb-thumbs"></div>' +
            '<textarea class="mmb-ta" id="mmb-ta" rows="1" maxlength="2000" placeholder="' + L('Ask about any dashboard, signal, or ticker…', '询问任意看板、信号或标的…') + '"></textarea>' +
            '<input type="file" id="mmb-file" accept="image/png,image/jpeg,image/webp,image/gif" multiple hidden>' +
            '<div class="mmb-tools">' +
              '<div class="mmb-seg" id="mmb-lane"><button data-lane="fast" class="on">⚡ ' + L('Fast', '快速') + '</button><button data-lane="pro">◈ Pro</button></div>' +
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
      researchBtn = $('.mmb-rpill'), thumbsEl = $('#mmb-thumbs'), fileEl = $('#mmb-file');

  /* ── state ── */
  var lane = 'fast', researchMode = false, threadId = null, streaming = false,
      quotas = {}, authed = false, ctxSymbol = '', streamAbort = null, pendingImages = [], proEligible = false;
  var MAX_IMAGES = 4;
  var explainPanel = null; /* set by MMBrain.explain(); attached once to the next send()'s context */

  function esc(s) { var d = DOC.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; }
  /* markdown-lite: paragraphs, bold, bullet lists — all HTML-escaped */
  function renderMd(t) {
    var lines = String(t || '').split('\n'), out = [], list = null;
    function flush() { if (list) { out.push('<ul>' + list.join('') + '</ul>'); list = null; } }
    for (var i = 0; i < lines.length; i++) {
      var ln = lines[i], m = ln.match(/^\s*[-*•]\s+(.*)/);
      var f = function (x) { return esc(x).replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>'); };
      if (m) { if (!list) list = []; list.push('<li>' + f(m[1]) + '</li>'); }
      else if (/^\s*#{1,4}\s+/.test(ln)) { flush(); out.push('<p><strong>' + f(ln.replace(/^\s*#{1,4}\s+/, '')) + '</strong></p>'); }
      else if (ln.trim()) { flush(); out.push('<p>' + f(ln) + '</p>'); }
      else flush();
    }
    flush(); return out.join('');
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
  function loadQuotas() {
    withAuth().then(function (h) { return fetch(API + '/api/brain/me', { headers: h, credentials: 'include' }); })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d) return; quotas = d.quotas || {};
        proEligible = !!(quotas.pro && quotas.pro.limit > 0);
        researchBtn.classList.toggle('mmb-off', !proEligible);
        if (!proEligible && researchMode) setResearch(false);
        renderQuota();
      }).catch(function () {});
  }
  function renderQuota() {
    var q = quotas[researchMode ? 'pro' : lane];
    if (!q) { qEl.textContent = ''; return; }
    qEl.textContent = (researchMode ? '◈ ' : (lane === 'pro' ? '◈ ' : '⚡ ')) + q.remaining + '/' + q.limit;
    qEl.className = 'mmb-q' + (q.remaining <= 0 ? ' empty' : (q.remaining <= Math.max(1, q.limit * 0.15) ? ' warn' : ''));
  }

  /* ── threads ── */
  function loadThreads() {
    withAuth().then(function (h) { return fetch(API + '/api/brain/threads', { headers: h, credentials: 'include' }); })
      .then(function (r) { return r.ok ? r.json() : { threads: [] }; })
      .then(function (d) { renderThreads((d && d.threads) || []); }).catch(function () {});
  }
  function renderThreads(threads) {
    if (!threads.length) { tlist.innerHTML = '<div class="mmb-th-empty">' + L('Your conversations appear here.', '你的对话会显示在这里。') + '</div>'; return; }
    tlist.innerHTML = '';
    threads.forEach(function (t) {
      var d = DOC.createElement('div'); d.className = 'mmb-ti' + (t.id === threadId ? ' on' : ''); d.dataset.id = t.id;
      var date = ''; try { date = new Date(t.updated_at).toLocaleDateString(); } catch (e) {}
      d.innerHTML = '<div class="tt">' + esc(t.title || L('Untitled', '未命名')) + '</div><div class="tm">' + esc(t.lane || 'fast') + ' · ' + esc(date) + '</div>';
      d.addEventListener('click', function () { openThread(t.id); if (!panel.classList.contains('max')) panel.classList.remove('show-side'); });
      tlist.appendChild(d);
    });
  }
  function openThread(id) {
    threadId = id;
    root.querySelectorAll('.mmb-ti').forEach(function (el) { el.classList.toggle('on', el.dataset.id === id); });
    withAuth().then(function (h) { return fetch(API + '/api/brain/threads/' + id, { headers: h, credentials: 'include' }); })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { if (!d) return; clearMsgs(); (d.messages || []).forEach(function (m) { appendMsg(m.role, m.content); }); }).catch(function () {});
  }

  /* ── messages ── */
  function clearMsgs() { scroll.innerHTML = ''; renderEmpty(); }
  function appendMsg(role, content) {
    var es = $('#mmb-emptystate'); if (es) es.remove();
    var d = DOC.createElement('div'); d.className = 'mmb-msg ' + role;
    var b = DOC.createElement('div'); b.className = 'mmb-bub';
    /* assistant bubbles keep charts (a sibling container) separate from the streamed
       text node, so replacing the text HTML on each delta never wipes an inline chart. */
    b.innerHTML = role === 'user' ? '<p>' + esc(content) + '</p>'
      : '<div class="mmb-charts"></div><div class="mmb-txt">' + renderMd(content) + '</div>';
    if (role === 'assistant') addCopyBtn(b);
    d.appendChild(b); scroll.appendChild(d); stick(); return b;
  }
  /* copy-answer affordance — a small clipboard button pinned top-right inside the bubble.
     Copies the rendered text (not charts) plus a short attribution line. */
  function addCopyBtn(b) {
    var cb = DOC.createElement('button'); cb.className = 'mmb-copy'; cb.title = 'Copy'; cb.innerHTML = CLIP;
    cb.addEventListener('click', function (e) {
      e.stopPropagation();
      var txt = (b.querySelector('.mmb-txt') || b).innerText || '';
      var payload = txt.trim() + '\n\n— Mastermind Brain · mastermind-x.com';
      try {
        if (!(navigator.clipboard && navigator.clipboard.writeText)) return;
        navigator.clipboard.writeText(payload).then(function () {
          cb.innerHTML = CHECK; setTimeout(function () { cb.innerHTML = CLIP; }, 1200);
        }).catch(function () {});
      } catch (e2) {}
    });
    b.appendChild(cb);
  }
  function bubTxt(b) { return b.querySelector('.mmb-txt') || b; }
  function stick() { if (scroll.scrollHeight - scroll.scrollTop - scroll.clientHeight < 90) scroll.scrollTop = scroll.scrollHeight; }

  var PROMPTS = [
    ['M3 3v18h18|M7 14l4-4 3 3 5-6', L('What regime are we in and what’s driving it?', '现在是什么市场周期？由什么驱动？')],
    ['M4 20V10M10 20V4M16 20v-7M22 20H2', L('Which themes have the strongest momentum?', '哪些主题动量最强？')],
    ['M12 3a9 9 0 1 0 9 9|M12 7v5l3 2', L('What should I be watching this week?', '这周该关注什么？')],
    ['M4 5h16M4 12h16M4 19h10', L('How is my watchlist doing?', '我的自选股表现如何？')]
  ];
  function renderEmpty() {
    var name = '';
    try { var u = window.MDXAuth && window.MDXAuth.user && window.MDXAuth.user(); if (u) { name = (u.user_metadata && (u.user_metadata.display_name || u.user_metadata.name)) || (u.email ? u.email.split('@')[0] : ''); } } catch (e) {}
    name = name ? (name.charAt(0).toUpperCase() + name.slice(1)) : '';
    var cards = PROMPTS.map(function (p) {
      var paths = p[0].split('|').map(function (d) { return '<path d="' + d + '"/>'; }).join('');
      return '<button class="mmb-cardp" data-p="' + esc(p[1]) + '"><div class="ci"><svg viewBox="0 0 24 24">' + paths + '</svg></div><span class="cp">' + esc(p[1]) + '</span></button>';
    }).join('');
    var hero = '<div class="mmb-empty" id="mmb-emptystate"><div class="mmb-hero"><h1>' +
      (name ? '<span class="g1">' + L('Hi there, ', '你好，') + '</span><span class="nm">' + esc(name) + '</span><br>' : '') +
      '<span class="g2">' + L('What do you want to know?', '你想了解什么？') + '</span></h1>' +
      '<p>' + L('Your desk copilot — it reads the live signals, regimes and flow on this dashboard and the Terminal, and explains what they mean.', '你的桌面副驾 — 读取本看板与终端的实时信号、周期与资金流，并解释其含义。') + '</p></div>' +
      '<div class="mmb-cards">' + cards + '</div></div>';
    scroll.innerHTML = hero;
  }

  /* ── send (SSE) ── */
  function send(text) {
    text = (text || ta.value).trim();
    var imgs = pendingImages.slice();
    if ((!text && !imgs.length) || streaming) return;
    if (!authed && window.MDXAuth && window.MDXAuth.enabled && window.MDXAuth.enabled()) { window.MDXAuth.open('signin'); return; }
    /* only the latest reply carries follow-up chips — clear any stale rows */
    root.querySelectorAll('.mmb-sugg').forEach(function (el) { el.remove(); });
    var ub = appendMsg('user', text);
    if (imgs.length) { /* show the attached images at the top of the user bubble */
      var iw = DOC.createElement('div'); iw.className = 'mmb-imgs';
      imgs.forEach(function (s) { var im = DOC.createElement('img'); im.src = s; iw.appendChild(im); });
      ub.insertBefore(iw, ub.firstChild);
    }
    pendingImages = []; renderThumbs();
    ta.value = ''; autosize(); sendBtn.disabled = true; streaming = true; upgradeEl.style.display = 'none';
    var typing = DOC.createElement('div'); typing.className = 'mmb-msg assistant'; typing.innerHTML = '<div class="mmb-bub"><span class="mmb-typing"><span></span><span></span><span></span></span></div>';
    scroll.appendChild(typing); stick();
    var bub = null, acc = '', steps = null, suggestions = null;
    var ctx = { page: (ANCHOR === 'top' ? 'terminal' : 'dashboard') }; if (ctxSymbol) ctx.symbol = ctxSymbol;
    /* an "explain this panel" request carries the panel key once, then clears */
    if (explainPanel) { ctx.panel = explainPanel; explainPanel = null; }
    var apiText = text || L('Please analyze the attached image.', '请分析所附图片。');
    var body = JSON.stringify({ message: apiText, lane: researchMode ? 'pro' : lane, mode: researchMode ? 'research' : 'chat', thread_id: threadId || undefined, context: ctx, images: imgs.length ? imgs : undefined });
    if (streamAbort) streamAbort.abort();
    var ac = (typeof AbortController !== 'undefined') ? new AbortController() : null; streamAbort = ac;
    withAuth({ 'Content-Type': 'application/json' }).then(function (h) {
      return fetch(API + '/api/brain/stream', { method: 'POST', headers: h, credentials: 'include', body: body, signal: ac ? ac.signal : undefined });
    }).then(function (res) {
      if (res.status === 401) { typing.remove(); streaming = false; syncSend(); if (window.MDXAuth && window.MDXAuth.enabled()) window.MDXAuth.open('signin'); else if (CFG.onAuthRequired) { try { CFG.onAuthRequired(); } catch (e) {} } return; }
      if (res.status === 402) { typing.remove(); streaming = false; syncSend(); return res.json().then(showUpgrade).catch(function () { showUpgrade({}); }); }
      if (!res.ok || !res.body) { typing.remove(); bub = appendMsg('assistant', ''); bub.innerHTML = '<p>' + L('Something went wrong. Please try again.', '出错了，请重试。') + '</p>'; streaming = false; syncSend(); return; }
      var reader = res.body.getReader(), dec = new TextDecoder(), buf = '';
      function ensureBub() { if (!bub) { typing.remove(); bub = appendMsg('assistant', ''); } return bub; }
      function pump() {
        return reader.read().then(function (r) {
          if (r.done) { finish(); return; }
          buf += dec.decode(r.value, { stream: true }); var lines = buf.split('\n'); buf = lines.pop() || '';
          lines.forEach(function (ln) {
            ln = ln.trim(); if (ln.indexOf('data:') !== 0) return; var data = ln.slice(5).trim(); if (!data) return;
            var j; try { j = JSON.parse(data); } catch (e) { return; }
            if (j.type === 'meta') { if (j.thread_id) threadId = j.thread_id; if (j.quota) { quotas[j.quota.lane] = j.quota; renderQuota(); } }
            else if (j.type === 'tool') { ensureBub(); if (!steps) { steps = DOC.createElement('div'); steps.className = 'mmb-tool'; steps.textContent = L('Reading ', '正在读取 ') + (j.name || '') + '…'; bub.parentNode.insertBefore(steps, bub); } else steps.textContent = L('Reading ', '正在读取 ') + (j.name || '') + '…'; stick(); }
            else if (j.type === 'chart' && j.svg) { ensureBub(); var cw = DOC.createElement('div'); cw.className = 'mmb-chart'; cw.innerHTML = j.svg; (bub.querySelector('.mmb-charts') || bub).appendChild(cw); stick(); }
            else if (j.type === 'delta') { ensureBub(); if (steps) { steps.remove(); steps = null; } acc += j.text; bubTxt(bub).innerHTML = renderMd(acc); stick(); }
            else if (j.type === 'suggest') { if (j.items && j.items.length) suggestions = j.items.slice(0, 3); }
            /* host bridges (Terminal): chart-command + annotate events are executed by the
               host page, not the widget — forward them to the CFG callbacks when provided. */
            else if (j.type === 'command') { try { if (CFG.onCommand) CFG.onCommand(j); } catch (e) {} }
            else if (j.type === 'annotate') { try { if (CFG.onAnnotate) CFG.onAnnotate(j); } catch (e) {} }
            else if (j.type === 'done') { ensureBub(); if (steps) { steps.remove(); steps = null; } if (acc) bubTxt(bub).innerHTML = renderMd(acc); if (j.citations && j.citations.length) addCites(bub, j.citations); if (suggestions && suggestions.length) addSuggest(bub, suggestions); if (j.quota) { quotas[j.quota.lane] = j.quota; renderQuota(); } stick(); }
            else if (j.type === 'error') { ensureBub(); acc += (acc ? '\n\n' : '') + '_' + (j.message || 'error') + '_'; bubTxt(bub).innerHTML = renderMd(acc); }
          });
          return pump();
        });
      }
      function finish() { streaming = false; syncSend(); loadThreads(); }
      return pump();
    }).catch(function () { typing.remove(); streaming = false; syncSend(); });
  }
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
    if (wrap.childNodes.length) { bub.parentNode.appendChild(wrap); stick(); }
  }
  function addCites(bub, cites) {
    var wrap = DOC.createElement('div'); wrap.className = 'mmb-cites';
    cites.slice(0, 8).forEach(function (c) {
      var a = DOC.createElement('a'); a.className = 'mmb-cite'; a.textContent = String(c).replace(/\.(json|parquet)$/, '').split('/').pop();
      var page = citeToPage(c); if (page) { a.href = page; a.target = '_blank'; }
      wrap.appendChild(a);
    });
    bub.parentNode.appendChild(wrap); stick();
  }
  function citeToPage(c) {
    c = String(c);
    if (/master_brief|world_state|regime/.test(c)) return (ANCHOR === 'top' ? 'https://mastermind-x.com/' : '') + 'macro.html';
    if (/options|gex|flow/.test(c)) return (ANCHOR === 'top' ? 'https://mastermind-x.com/' : '') + 'options_hub.html';
    if (/factor/.test(c)) return (ANCHOR === 'top' ? 'https://mastermind-x.com/' : '') + 'factors.html';
    return null;
  }
  function showUpgrade(d) {
    upgradeEl.style.display = 'block';
    var plansHref = (ANCHOR === 'top' ? 'https://mastermind-x.com/' : '') + 'plans.html';
    var link = '<a href="' + plansHref + '" target="_blank">' + L('See plans', '查看套餐') + '</a>';
    if (d && d.feature === 'vision') {
      upgradeEl.innerHTML = '<strong>' + L('Image analysis is a Pro feature', '图像分析为 Pro 功能') + '</strong> — ' +
        L('upgrade to attach charts and screenshots. ', '升级即可上传图表与截图。') + link;
    } else {
      upgradeEl.innerHTML = '<strong>' + L('Quota reached', '配额已用尽') + '</strong> — ' +
        L('upgrade to keep chatting. ', '升级以继续对话。') + link;
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
  function newChat() { threadId = null; pendingImages = []; renderThumbs(); root.querySelectorAll('.mmb-ti').forEach(function (el) { el.classList.remove('on'); }); clearMsgs(); if (!panel.classList.contains('max')) panel.classList.remove('show-side'); }

  /* ── auth wiring ── */
  function onAuth(user) {
    authed = !!user;
    var gate = $('#mmb-gate');
    if (authed) { if (gate) gate.remove(); if (!scroll.querySelector('.mmb-msg') && !$('#mmb-emptystate')) renderEmpty(); if (panel.classList.contains('open')) { loadThreads(); loadQuotas(); } showChat(true); }
    else { showChat(false); }
  }
  function showChat(on) {
    var comp = root.querySelector('.mmb-comp'); comp.style.display = on ? '' : 'none'; scroll.style.display = on ? '' : 'none';
    var gate = $('#mmb-gate');
    if (!on && !gate) {
      var g = DOC.createElement('div'); g.id = 'mmb-gate'; g.className = 'mmb-gate';
      g.innerHTML = '<div class="mmb-orb">' + ORB + '</div><h2>' + L('Ask the Mastermind', '问操盘大脑') + '</h2>' +
        '<p>' + L('One brain across every dashboard and the Terminal. Sign in to begin.', '贯通所有看板与终端的同一个大脑。登录即可开始。') + '</p>' +
        '<button class="mmb-signin" data-act="signin">' + L('Sign in', '登录') + '</button>';
      root.querySelector('.mmb-main').insertBefore(g, root.querySelector('.mmb-comp'));
    } else if (on && gate) gate.remove();
  }

  /* ── events (delegated) ── */
  root.addEventListener('click', function (e) {
    var rm = e.target.closest('[data-rmimg]');
    if (rm) { pendingImages.splice(+rm.dataset.rmimg, 1); renderThumbs(); return; }
    var t = e.target.closest('[data-act],[data-p],[data-lane]'); if (!t) return;
    if (t.dataset.p) { ta.value = t.dataset.p; autosize(); send(); return; }
    if (t.dataset.lane) { lane = t.dataset.lane; root.querySelectorAll('#mmb-lane button').forEach(function (b) { b.classList.toggle('on', b === t); }); renderQuota(); return; }
    var a = t.dataset.act;
    if (a === 'close') close(); else if (a === 'max') toggleMax(); else if (a === 'side') toggleSide();
    else if (a === 'new') newChat(); else if (a === 'research') setResearch(!researchMode);
    else if (a === 'home') location.href = (ANCHOR === 'top' ? 'https://mastermind-x.com/' : '') + 'macro.html';
    else if (a === 'voice') startVoice();
    else if (a === 'attach') { if (proEligible) fileEl.click(); else showUpgrade({ feature: 'vision' }); }
    else if (a === 'signin') { if (window.MDXAuth) window.MDXAuth.open('signin'); }
  });
  fileEl.addEventListener('change', function () { addFiles(fileEl.files); fileEl.value = ''; });
  if (launch) launch.addEventListener('click', open);
  scrim.addEventListener('click', close);
  sendBtn.addEventListener('click', function () { send(); });
  ta.addEventListener('input', function () { autosize(); syncSend(); });
  ta.addEventListener('keydown', function (e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } });
  ta.addEventListener('paste', function (e) { /* paste a screenshot straight in */
    var items = (e.clipboardData && e.clipboardData.items) || []; var files = [];
    for (var i = 0; i < items.length; i++) { if (items[i].type && items[i].type.indexOf('image/') === 0) { var f = items[i].getAsFile(); if (f) files.push(f); } }
    if (files.length) { e.preventDefault(); addFiles(files); }
  });
  DOC.addEventListener('keydown', function (e) { if (e.key === 'Escape' && panel.classList.contains('open')) close(); });

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
  function startVoice() {
    var SR = window.SpeechRecognition || window.webkitSpeechRecognition; if (!SR) return;
    var r = new SR(); r.lang = zh() ? 'zh-CN' : 'en-US'; r.interimResults = false;
    r.onresult = function (ev) { ta.value = (ta.value + ' ' + ev.results[0][0].transcript).trim(); autosize(); sendBtn.disabled = !ta.value.trim(); };
    try { r.start(); } catch (e) {}
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
