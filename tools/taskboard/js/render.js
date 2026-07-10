/* Slate — rendering: topbar, canvas, boards, cards */
'use strict';

const CANVAS_W = 6000, CANVAS_H = 4000;
const BOARD_W = 300, TIDY_GAP = 24, TIDY_ORIGIN = 48;

function applyTheme() {
  document.documentElement.dataset.theme = state.theme;
  const sun = $('#themeIconSun'), moon = $('#themeIconMoon');
  if (sun && moon) {
    sun.style.display = state.theme === 'dark' ? 'none' : '';
    moon.style.display = state.theme === 'dark' ? '' : 'none';
  }
  // live browser chrome tracks the theme; manifest.webmanifest colors are static JSON
  // (no per-theme mechanism exists), so the PWA install splash always uses the light value
  const meta = $('meta[name="theme-color"]');
  if (meta) meta.content = state.theme === 'dark' ? '#0F1216' : '#F5F6F8';
}

function renderTopbar() {
  const brain = state.view === 'brain';
  $('#wsName').textContent = activeWs().name;
  document.title = brain ? 'Brain — Slate' : activeWs().name + ' — Slate';
  $$('#viewSeg .seg-btn').forEach(b => b.classList.toggle('active', (state.view || 'tasks') === b.dataset.view));
  $$('#brainTabs .seg-btn').forEach(b => b.classList.toggle('active', brainTab === b.dataset.tab));
}

function renderCanvas() {
  const ws = activeWs();
  const canvas = $('#canvas');
  canvas.style.width = CANVAS_W + 'px';
  canvas.style.height = CANVAS_H + 'px';
  canvas.textContent = '';
  for (const b of ws.boards) canvas.appendChild(boardEl(b));
  $('#hint').textContent = 'Double-click anywhere to start a board';
  $('#hint').hidden = ws.boards.length > 0;
  const vp = $('#viewport');
  vp.scrollLeft = ws.scroll.x || 0;
  vp.scrollTop = ws.scroll.y || 0;
}

function rerenderBoard(boardId) {
  // state is already mutated by the caller; in Brain view there is no tasks DOM to
  // patch (renderCanvas rebuilds it on switch), and appending here would leak a
  // board into the Brain canvas
  if (state.view === 'brain') return;
  const b = findBoard(boardId);
  const old = $('.board[data-id="' + boardId + '"]');
  if (!b) { if (old) old.remove(); return; }
  // an open composer's unsubmitted text must survive the re-render
  let draft = null;
  if (old) {
    const compTitle = $('.composer-title', old);
    if (compTitle) {
      const compDesc = $('.composer-desc', old);
      draft = {
        t: compTitle.value,
        d: compDesc ? compDesc.value : '',
        dHidden: compDesc ? compDesc.hidden : true,
        focused: old.contains(document.activeElement),
      };
    }
  }
  const fresh = boardEl(b);
  if (old) {
    fresh.style.zIndex = old.style.zIndex;
    old.replaceWith(fresh);
  } else {
    $('#canvas').appendChild(fresh);
  }
  if (draft) openComposer(fresh, b, draft);
  if (state.view !== 'brain') $('#hint').hidden = activeWs().boards.length > 0;
}

function boardEl(b) {
  const root = el('section', 'board');
  root.dataset.id = b.id;
  root.style.left = b.x + 'px';
  root.style.top = b.y + 'px';

  const head = el('header', 'board-head');
  const title = el('h2', 'board-title', b.name);
  title.title = 'Double-click to rename';
  const count = el('span', 'board-count', String(b.cards.length));
  const menuBtn = el('button', 'ghost-btn board-menu-btn');
  menuBtn.title = 'Board actions';
  menuBtn.appendChild(svgIcon(ICONS.dots, 15, 2.2));
  head.append(title, count, menuBtn);
  root.appendChild(head);

  const list = el('div', 'cards');
  list.dataset.boardId = b.id;
  for (const c of b.cards) list.appendChild(cardEl(c, b));
  root.appendChild(list);

  const foot = el('footer', 'board-foot');
  const addBtn = el('button', 'add-card-btn');
  addBtn.appendChild(svgIcon(ICONS.plus, 13, 1.8));
  addBtn.appendChild(el('span', null, 'Add a card'));
  foot.appendChild(addBtn);
  root.appendChild(foot);

  if (b.done.length) {
    const doneBar = el('button', 'done-bar');
    const check = el('span', 'done-bar-check');
    check.appendChild(svgIcon(ICONS.check, 11, 2));
    doneBar.append(check, el('span', 'done-bar-label', b.done.length + ' done'));
    const chev = el('span', 'done-bar-chev' + (b.showDone ? ' open' : ''));
    chev.appendChild(svgIcon('M4 6l4 4 4-4', 12, 1.8));
    doneBar.appendChild(chev);
    root.appendChild(doneBar);
    if (b.showDone) {
      const doneList = el('div', 'done-list');
      for (const c of b.done) doneList.appendChild(doneCardEl(c, b));
      const clear = el('button', 'done-clear', 'Clear ' + b.done.length + ' completed');
      doneList.appendChild(clear);
      root.appendChild(doneList);
    }
  }
  return root;
}

function cardEl(c, board) {
  const root = el('article', 'card' + (c.color ? ' tint-' + c.color : ''));
  root.dataset.id = c.id;

  const row = el('div', 'card-row');
  const circle = el('button', 'complete-circle');
  circle.title = 'Mark complete';
  circle.setAttribute('aria-label', 'Mark complete');
  const ns = 'http://www.w3.org/2000/svg';
  const csvg = document.createElementNS(ns, 'svg');
  csvg.setAttribute('viewBox', '0 0 16 16');
  csvg.classList.add('circle-svg');
  const ring = document.createElementNS(ns, 'circle');
  ring.setAttribute('cx', 8); ring.setAttribute('cy', 8); ring.setAttribute('r', 6.6);
  ring.classList.add('ring');
  const tick = document.createElementNS(ns, 'path');
  tick.setAttribute('d', 'M5 8.4l2.1 2.1L11 6');
  tick.classList.add('tick');
  csvg.append(ring, tick);
  circle.appendChild(csvg);
  const title = el('div', 'card-title', c.t);
  row.append(circle, title);
  root.appendChild(row);

  const meta = cardMetaEl(c);
  if (meta) root.appendChild(meta);
  const att = cardAttachmentsEl(c);
  if (att) root.appendChild(att);
  return root;
}

function cardMetaEl(c) {
  const bits = [];
  if (c.due) {
    const st = dueStatus(c.due);
    const chip = el('span', 'chip due-chip due-' + st);
    chip.appendChild(svgIcon(ICONS.clock, 11, 1.6));
    chip.appendChild(el('span', null, st === 'today' ? 'Today' : fmtDate(c.due)));
    bits.push(chip);
  }
  for (const t of c.tags) {
    const chip = el('span', 'chip tag-chip tint-' + tagColor(t), t);
    bits.push(chip);
  }
  if (c.d && c.d.trim()) {
    const d = el('span', 'chip desc-chip');
    d.title = 'Has a description';
    d.appendChild(svgIcon(ICONS.text, 11, 1.6));
    bits.push(d);
  }
  if (!bits.length) return null;
  const meta = el('div', 'card-meta');
  bits.forEach(x => meta.appendChild(x));
  return meta;
}

function cardAttachmentsEl(c) {
  if (!c.at.length) return null;
  const wrap = el('div', 'card-atts');
  for (const a of c.at) {
    const btn = el('button', 'att');
    btn.dataset.attId = a.id;
    btn.title = a.name;
    if (a.thumb) {
      btn.classList.add('att-img');
      const img = el('img');
      img.alt = a.name;
      img.src = a.thumb;
      img.draggable = false;
      btn.appendChild(img);
    } else {
      btn.classList.add('att-file');
      btn.appendChild(svgIcon(ICONS.file, 13, 1.4));
      btn.appendChild(el('span', 'att-ext', extOf(a.name)));
    }
    wrap.appendChild(btn);
  }
  return wrap;
}
function extOf(name) {
  const m = name.match(/\.([a-z0-9]{1,5})$/i);
  return m ? m[1].toUpperCase() : 'FILE';
}

function doneCardEl(c, board) {
  const root = el('article', 'card done-card');
  root.dataset.id = c.id;
  const row = el('div', 'card-row');
  const circle = el('button', 'complete-circle filled');
  circle.title = 'Restore card';
  circle.setAttribute('aria-label', 'Restore card');
  circle.appendChild(svgIcon(ICONS.check, 11, 2));
  const title = el('div', 'card-title', c.t);
  row.append(circle, title);
  root.appendChild(row);
  return root;
}

/* full re-render, dispatching on the active view */
let lastViewRendered = null;
function renderAll() {
  applyTheme();
  document.body.dataset.view = state.view || 'tasks';
  document.body.dataset.tab = state.view === 'brain' ? brainTab : 'board';
  renderTopbar();
  const viewChanged = lastViewRendered !== state.view;
  lastViewRendered = state.view;
  if (state.view === 'brain') {
    renderBrain();
  } else {
    lastBrainTabRendered = null; // next brain entry is a fresh tab entry
    renderCanvas();
  }
  if (viewChanged) fadeIn($('#viewport'));
}

function fadeIn(node) {
  if (!node) return;
  node.classList.remove('view-enter');
  node.getBoundingClientRect();
  node.classList.add('view-enter');
  setTimeout(() => node.classList.remove('view-enter'), 260);
}
