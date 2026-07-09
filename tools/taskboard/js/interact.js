/* Slate — interactions: canvas pan, double-click create, board drag, tidy, card drag-and-drop */
'use strict';

const DRAG_THRESHOLD = 5;

/* ---------- z ordering ---------- */
function bringToFront(boardNode) {
  zCounter += 1;
  boardNode.style.zIndex = zCounter;
}

/* ---------- canvas: pan by dragging empty space, double-click to create ---------- */
(function canvasInteractions() {
  const vp = $('#viewport');
  const canvas = $('#canvas');
  let pan = null;

  vp.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    if (e.target !== canvas && e.target !== vp) return;
    pan = { x: e.clientX, y: e.clientY, sl: vp.scrollLeft, st: vp.scrollTop, moved: false };
  });
  window.addEventListener('pointermove', (e) => {
    if (!pan) return;
    const dx = e.clientX - pan.x, dy = e.clientY - pan.y;
    if (!pan.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD) return;
    pan.moved = true;
    vp.classList.add('panning');
    vp.scrollLeft = pan.sl - dx;
    vp.scrollTop = pan.st - dy;
  });
  window.addEventListener('pointerup', () => {
    if (!pan) return;
    if (pan.moved) saveScroll();
    vp.classList.remove('panning');
    pan = null;
  });
  window.addEventListener('pointercancel', () => {
    if (!pan) return;
    vp.classList.remove('panning');
    pan = null;
  });
  vp.addEventListener('scroll', debounce(saveScroll, 300));

  function saveScroll() {
    if (state.view === 'brain') { // brain scroll is session-only, and never clobbers workspace scroll
      if (brainTab === 'board') { brainScroll.x = vp.scrollLeft; brainScroll.y = vp.scrollTop; }
      return;
    }
    const ws = activeWs();
    ws.scroll.x = vp.scrollLeft;
    ws.scroll.y = vp.scrollTop;
    save();
  }

  canvas.addEventListener('dblclick', (e) => {
    if (state.view === 'brain') return; // the Brain board creates notes instead (js/brain.js)
    if (e.target !== canvas) return;
    const r = canvas.getBoundingClientRect();
    const x = clamp(e.clientX - r.left - BOARD_W / 2, 8, CANVAS_W - BOARD_W - 8);
    const y = clamp(e.clientY - r.top - 20, 8, CANVAS_H - 100);
    createBoardAt(x, y);
  });
})();

/* while a drag is live, stop touch gestures from scrolling underneath it */
const suppressTouchScroll = (e) => e.preventDefault();
function lockTouchScroll() { document.addEventListener('touchmove', suppressTouchScroll, { passive: false }); }
function unlockTouchScroll() { document.removeEventListener('touchmove', suppressTouchScroll); }

function createBoardAt(x, y) {
  const b = newBoard('', x, y);
  activeWs().boards.push(b);
  save();
  const node = boardEl(b);
  node.classList.add('board-enter');
  $('#canvas').appendChild(node);
  bringToFront(node);
  $('#hint').hidden = true;
  startBoardRename(node, b, true);
}

/* ---------- board dragging (by header) ---------- */
(function boardDrag() {
  const canvas = $('#canvas');
  let drag = null;

  canvas.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    const head = e.target.closest('.board-head');
    if (!head) return;
    if (e.target.closest('button, input, textarea, [contenteditable]')) return;
    const node = head.closest('.board');
    const b = findBoard(node.dataset.id);
    if (!b) return;
    bringToFront(node);
    drag = { node, b, startX: e.clientX, startY: e.clientY, origX: b.x, origY: b.y, h: node.offsetHeight, moved: false };
    e.preventDefault();
  });

  window.addEventListener('pointermove', (e) => {
    if (!drag) return;
    const dx = e.clientX - drag.startX, dy = e.clientY - drag.startY;
    if (!drag.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD) return;
    if (!drag.moved) { drag.moved = true; drag.node.classList.add('board-dragging'); document.body.classList.add('dragging-any'); }
    const nx = clamp(drag.origX + dx, 0, CANVAS_W - BOARD_W);
    const ny = clamp(drag.origY + dy, 0, CANVAS_H - Math.max(60, drag.h));
    drag.node.style.left = nx + 'px';
    drag.node.style.top = ny + 'px';
    autoscrollViewport(e);
  });

  function finishBoardDrag() {
    drag.node.classList.remove('board-dragging');
    document.body.classList.remove('dragging-any');
    stopAutoscroll();
    drag = null;
  }
  window.addEventListener('pointerup', () => {
    if (!drag) return;
    if (drag.moved) {
      drag.b.x = parseInt(drag.node.style.left, 10);
      drag.b.y = parseInt(drag.node.style.top, 10);
      save();
    }
    finishBoardDrag();
  });
  window.addEventListener('pointercancel', () => {
    if (!drag) return;
    drag.node.style.left = drag.origX + 'px';
    drag.node.style.top = drag.origY + 'px';
    finishBoardDrag();
  });
})();

/* ---------- tidy: snap boards into a grid, ordered by current position ---------- */
function tidyBoards() {
  const ws = activeWs();
  if (!ws.boards.length) return;
  const vp = $('#viewport');
  const cols = Math.max(1, Math.floor((vp.clientWidth - TIDY_ORIGIN) / (BOARD_W + TIDY_GAP)));
  // order by visual reading position: row bands, then x
  const sorted = [...ws.boards].sort((a, b2) => {
    const ra = Math.round(a.y / 260), rb = Math.round(b2.y / 260);
    return ra - rb || a.x - b2.x || a.y - b2.y;
  });
  // masonry into shortest column, honoring rendered heights
  const heights = new Array(cols).fill(TIDY_ORIGIN - 8);
  for (const b of sorted) {
    const node = $('.board[data-id="' + b.id + '"]');
    const h = node ? node.offsetHeight : 200;
    let col = 0;
    for (let i = 1; i < cols; i++) if (heights[i] < heights[col]) col = i;
    b.x = TIDY_ORIGIN + col * (BOARD_W + TIDY_GAP);
    b.y = heights[col] + (heights[col] > TIDY_ORIGIN - 8 ? TIDY_GAP : 8);
    heights[col] = b.y + h;
  }
  save();
  // animate to new spots
  for (const b of ws.boards) {
    const node = $('.board[data-id="' + b.id + '"]');
    if (!node) continue;
    node.classList.add('tidying');
    node.style.left = b.x + 'px';
    node.style.top = b.y + 'px';
  }
  setTimeout(() => $$('.board').forEach(n => n.classList.remove('tidying')), 450);
  vp.scrollTo({ left: 0, top: 0, behavior: 'smooth' });
}

/* ---------- FLIP helper for smooth sibling shifts ---------- */
function flip(nodes, mutate) {
  const rects = new Map();
  nodes.forEach(n => rects.set(n, n.getBoundingClientRect()));
  mutate();
  nodes.forEach(n => {
    const a = rects.get(n);
    if (!a || !n.isConnected) return;
    const b = n.getBoundingClientRect();
    const dy = a.top - b.top, dx = a.left - b.left;
    if (!dx && !dy) return;
    n.style.transition = 'none';
    n.style.transform = 'translate(' + dx + 'px,' + dy + 'px)';
    n.getBoundingClientRect(); // force reflow
    n.style.transition = 'transform 180ms cubic-bezier(.2,.7,.3,1)';
    n.style.transform = '';
    n.addEventListener('transitionend', () => { n.style.transition = ''; }, { once: true });
  });
}

/* ---------- viewport autoscroll during drags ---------- */
let autoscrollRAF = null;
let autoscrollVec = { x: 0, y: 0 };
function autoscrollViewport(e) {
  const vp = $('#viewport');
  const r = vp.getBoundingClientRect();
  const M = 48, SPEED = 14;
  autoscrollVec.x = e.clientX < r.left + M ? -SPEED : e.clientX > r.right - M ? SPEED : 0;
  autoscrollVec.y = e.clientY < r.top + M ? -SPEED : e.clientY > r.bottom - M ? SPEED : 0;
  if ((autoscrollVec.x || autoscrollVec.y) && !autoscrollRAF) {
    const step = () => {
      if (!autoscrollVec.x && !autoscrollVec.y) { autoscrollRAF = null; return; }
      vp.scrollLeft += autoscrollVec.x;
      vp.scrollTop += autoscrollVec.y;
      autoscrollRAF = requestAnimationFrame(step);
    };
    autoscrollRAF = requestAnimationFrame(step);
  }
}
function stopAutoscroll() {
  autoscrollVec.x = 0; autoscrollVec.y = 0;
  if (autoscrollRAF) { cancelAnimationFrame(autoscrollRAF); autoscrollRAF = null; }
}

/* ---------- card drag-and-drop (pointer-based, ghost + placeholder) ---------- */
(function cardDrag() {
  const canvas = $('#canvas');
  let press = null;   // pending press before threshold
  let drag = null;    // active drag

  canvas.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    const cardNode = e.target.closest('.card');
    if (!cardNode || cardNode.classList.contains('done-card')) return;
    if (e.target.closest('button, a, input, textarea')) return;
    press = { cardNode, x: e.clientX, y: e.clientY, lx: e.clientX, ly: e.clientY };
    if (e.pointerType === 'touch') {
      // touch: long-press to lift a card; quick swipes stay native scrolls
      press.timer = setTimeout(() => {
        if (press && !drag) {
          startCardDrag({ clientX: press.lx, clientY: press.ly });
          if (navigator.vibrate) navigator.vibrate(8);
        }
      }, 330);
    }
  });

  window.addEventListener('pointermove', (e) => {
    if (press && !drag) {
      press.lx = e.clientX; press.ly = e.clientY;
      const dist = Math.hypot(e.clientX - press.x, e.clientY - press.y);
      if (press.timer) { // touch press pending: movement means the user is scrolling
        if (dist >= 8) { clearTimeout(press.timer); press = null; }
        return;
      }
      if (dist >= DRAG_THRESHOLD) startCardDrag(e);
      return;
    }
    if (drag) moveCardDrag(e);
  });

  window.addEventListener('pointerup', (e) => {
    if (press && press.timer) clearTimeout(press.timer);
    if (drag) endCardDrag(e);
    press = null;
  });
  window.addEventListener('pointercancel', () => {
    if (press && press.timer) clearTimeout(press.timer);
    if (drag) cancelCardDrag();
    press = null;
  });

  function startCardDrag(e) {
    const cardNode = press.cardNode;
    const id = cardNode.dataset.id;
    const found = findCard(id);
    if (!found || found.done) { press = null; return; }
    const rect = cardNode.getBoundingClientRect();

    const ghost = cardNode.cloneNode(true);
    ghost.classList.add('card-ghost');
    ghost.style.width = rect.width + 'px';
    ghost.style.left = '0px';
    ghost.style.top = '0px';
    document.body.appendChild(ghost);

    const placeholder = el('div', 'card-placeholder');
    placeholder.style.height = rect.height + 'px';
    cardNode.replaceWith(placeholder);

    drag = {
      id, card: found.card, fromBoard: found.board,
      ghost, placeholder,
      offX: press.x - rect.left, offY: press.y - rect.top,
      w: rect.width,
    };
    document.body.classList.add('dragging-any');
    lockTouchScroll();
    positionGhost(e);
    press = null;
  }

  function positionGhost(e) {
    drag.ghost.style.transform = 'translate(' + (e.clientX - drag.offX) + 'px,' + (e.clientY - drag.offY) + 'px) rotate(2.5deg)';
  }

  function moveCardDrag(e) {
    positionGhost(e);
    autoscrollViewport(e);
    drag.ghost.style.pointerEvents = 'none';
    const under = document.elementFromPoint(e.clientX, e.clientY);
    if (!under) return;
    const list = under.closest('.cards');
    const boardNode = under.closest('.board');
    const targetList = list || (boardNode ? $('.cards', boardNode) : null);
    if (!targetList) return;

    // autoscroll inside the card list
    const lr = targetList.getBoundingClientRect();
    if (e.clientY < lr.top + 32) targetList.scrollTop -= 8;
    else if (e.clientY > lr.bottom - 32) targetList.scrollTop += 8;

    // compute insertion point among visible cards (excluding placeholder)
    const siblings = $$('.card', targetList).filter(n => !n.classList.contains('done-card'));
    let before = null;
    for (const sib of siblings) {
      const r = sib.getBoundingClientRect();
      if (e.clientY < r.top + r.height / 2) { before = sib; break; }
    }
    const ph = drag.placeholder;
    if (before === ph || (ph.parentNode === targetList && ph.nextElementSibling === before)) return;
    const affected = [...siblings, ...$$('.card-placeholder')];
    flip(affected, () => {
      if (before) targetList.insertBefore(ph, before);
      else targetList.appendChild(ph);
    });
  }

  function endCardDrag(e) {
    const { placeholder, ghost, card, fromBoard } = drag;
    const targetList = placeholder.closest('.cards');
    const toBoard = targetList ? findBoard(targetList.dataset.boardId) : fromBoard;

    // state: remove from source
    const fromIdx = fromBoard.cards.indexOf(card);
    if (fromIdx >= 0) fromBoard.cards.splice(fromIdx, 1);
    // state: insert at placeholder position
    let insertIdx = 0;
    for (const n of $$('.card, .card-placeholder', targetList)) {
      if (n === placeholder) break;
      if (n.classList.contains('card') && !n.classList.contains('done-card')) insertIdx++;
    }
    toBoard.cards.splice(clamp(insertIdx, 0, toBoard.cards.length), 0, card);
    save();

    // animate ghost into place, then re-render both boards
    const pr = placeholder.getBoundingClientRect();
    ghost.style.transition = 'transform 160ms cubic-bezier(.2,.7,.3,1)';
    ghost.style.transform = 'translate(' + pr.left + 'px,' + pr.top + 'px) rotate(0deg)';
    const finish = () => {
      ghost.remove();
      rerenderBoard(fromBoard.id);
      if (toBoard.id !== fromBoard.id) rerenderBoard(toBoard.id);
    };
    ghost.addEventListener('transitionend', finish, { once: true });
    setTimeout(finish, 220); // safety net
    document.body.classList.remove('dragging-any');
    unlockTouchScroll();
    stopAutoscroll();
    drag = null;
  }

  function cancelCardDrag() {
    drag.ghost.remove();
    rerenderBoard(drag.fromBoard.id);
    document.body.classList.remove('dragging-any');
    unlockTouchScroll();
    stopAutoscroll();
    drag = null;
  }
})();
