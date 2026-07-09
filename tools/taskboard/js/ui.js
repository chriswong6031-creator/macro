/* Slate — UI components: toasts, undo, popovers, lightbox, composer, complete ritual, board menu, file drops */
'use strict';

/* ---------- toasts + single-slot undo ---------- */
let toastTimer = null;
function toast(msg, opts) {
  opts = opts || {};
  const root = $('#toastRoot');
  root.textContent = '';
  const t = el('div', 'toast' + (opts.tone ? ' toast-' + opts.tone : ''));
  t.appendChild(el('span', 'toast-msg', msg));
  if (opts.action) {
    const btn = el('button', 'toast-action', opts.action.label);
    btn.addEventListener('click', () => { opts.action.fn(); dismissToast(); });
    t.appendChild(btn);
  }
  root.appendChild(t);
  requestAnimationFrame(() => t.classList.add('show'));
  clearTimeout(toastTimer);
  toastTimer = setTimeout(dismissToast, opts.ms || (opts.action ? 6000 : 3200));
}
function dismissToast() {
  const t = $('#toastRoot .toast');
  if (!t) return;
  t.classList.remove('show');
  setTimeout(() => t.remove(), 220);
}
function undoableToast(msg, revert) {
  toast(msg, { action: { label: 'Undo', fn: () => { revert(); save(); renderAll(); } } });
}

/* ---------- popover ---------- */
let activePopoverClose = null;
function openPopover(anchor, build, opts) {
  closePopover();
  const root = $('#popoverRoot');
  const pop = el('div', 'popover' + ((opts && opts.cls) ? ' ' + opts.cls : ''));
  root.appendChild(pop);
  const close = () => {
    pop.remove();
    window.removeEventListener('mousedown', onOutside, true);
    window.removeEventListener('keydown', onKey, true);
    activePopoverClose = null;
  };
  build(pop, close);
  const r = anchor.getBoundingClientRect();
  pop.style.top = Math.min(r.bottom + 6, window.innerHeight - pop.offsetHeight - 12) + 'px';
  pop.style.left = clamp(r.left, 8, window.innerWidth - pop.offsetWidth - 8) + 'px';
  requestAnimationFrame(() => pop.classList.add('show'));
  function onOutside(e) { if (!pop.contains(e.target) && e.target !== anchor && !anchor.contains(e.target)) close(); }
  function onKey(e) { if (e.key === 'Escape') { e.stopPropagation(); close(); } }
  window.addEventListener('mousedown', onOutside, true);
  window.addEventListener('keydown', onKey, true);
  activePopoverClose = close;
  return close;
}
function closePopover() { if (activePopoverClose) activePopoverClose(); }
function popItem(label, icon, fn, cls) {
  const b = el('button', 'pop-item' + (cls ? ' ' + cls : ''));
  if (icon) b.appendChild(svgIcon(icon, 14, 1.5));
  b.appendChild(el('span', null, label));
  b.addEventListener('click', fn);
  return b;
}

/* ---------- lightbox ---------- */
function openLightbox(att, dataUrl) {
  const root = $('#lightboxRoot');
  root.textContent = '';
  const bg = el('div', 'lightbox');
  const fig = el('figure', 'lightbox-fig');
  const img = el('img');
  img.src = dataUrl;
  img.alt = att.name;
  const cap = el('figcaption', 'lightbox-cap');
  cap.appendChild(el('span', 'lightbox-name', att.name));
  const dl = el('button', 'lightbox-dl');
  dl.appendChild(svgIcon(ICONS.download, 14, 1.6));
  dl.appendChild(el('span', null, 'Download'));
  dl.addEventListener('click', (e) => {
    e.stopPropagation();
    const a = document.createElement('a');
    a.href = dataUrl; a.download = att.name;
    document.body.appendChild(a); a.click(); a.remove();
  });
  cap.appendChild(dl);
  fig.append(img, cap);
  bg.appendChild(fig);
  root.appendChild(bg);
  requestAnimationFrame(() => bg.classList.add('show'));
  const close = () => { bg.classList.remove('show'); setTimeout(() => bg.remove(), 200); window.removeEventListener('keydown', onKey); };
  bg.addEventListener('mousedown', (e) => { if (e.target === bg) close(); });
  function onKey(e) { if (e.key === 'Escape') close(); }
  window.addEventListener('keydown', onKey);
}

/* ---------- complete / restore ritual ---------- */
function completeCard(cardId) {
  const found = findCard(cardId);
  if (!found || found.done) return;
  // state-level re-entry guard: a mid-ritual re-render swaps the DOM node, so a class check is not enough
  if (found.card._completing) return;
  found.card._completing = true;
  const node = $('.card[data-id="' + cardId + '"]');
  const doMove = () => {
    delete found.card._completing;
    const idx = found.board.cards.indexOf(found.card);
    if (idx >= 0) found.board.cards.splice(idx, 1);
    found.card.completed = Date.now();
    if (!found.board.done.includes(found.card)) found.board.done.unshift(found.card);
    save();
    rerenderBoard(found.board.id);
  };
  if (!node) { doMove(); return; }
  node.classList.add('completing');
  setTimeout(() => {
    node.style.height = node.offsetHeight + 'px';
    node.getBoundingClientRect();
    node.classList.add('collapsing');
    node.style.height = '0px';
    setTimeout(doMove, 240);
  }, 420);
}
function restoreCard(cardId) {
  for (const b of activeWs().boards) {
    const i = b.done.findIndex(c => c.id === cardId);
    if (i >= 0) {
      const card = b.done.splice(i, 1)[0];
      card.completed = null;
      b.cards.push(card);
      save();
      rerenderBoard(b.id);
      return;
    }
  }
}

/* ---------- card composer ---------- */
function openComposer(boardNode, board, draft) {
  const foot = $('.board-foot', boardNode);
  if ($('.composer', boardNode)) { $('.composer textarea', boardNode).focus(); return; }
  foot.textContent = '';
  const comp = el('div', 'composer');
  const title = el('textarea', 'composer-title');
  title.rows = 1;
  title.placeholder = 'Card title';
  const desc = el('textarea', 'composer-desc');
  desc.rows = 2;
  desc.placeholder = 'Description';
  desc.hidden = true;
  const row = el('div', 'composer-row');
  const addBtn = el('button', 'primary-btn', 'Add card');
  const descBtn = el('button', 'ghost-btn composer-desc-btn');
  descBtn.title = 'Add a description';
  descBtn.appendChild(svgIcon(ICONS.text, 14, 1.6));
  const closeBtn = el('button', 'ghost-btn');
  closeBtn.title = 'Close';
  closeBtn.appendChild(svgIcon(ICONS.x, 13, 1.7));
  row.append(addBtn, descBtn, closeBtn);
  comp.append(title, desc, row);
  foot.appendChild(comp);
  autoGrow(title); autoGrow(desc);
  if (draft) {
    title.value = draft.t;
    desc.value = draft.d;
    desc.hidden = draft.dHidden;
    if (draft.focused) title.focus();
  } else {
    title.focus();
  }

  const closeComposer = () => { comp.remove(); rerenderBoard(board.id); };
  const submit = () => {
    const t = title.value.trim();
    if (!t) { title.focus(); return; }
    const card = newCard(t);
    if (!desc.hidden && desc.value.trim()) card.d = desc.value.trim();
    title.value = ''; desc.value = ''; // clear before rerender so the draft-preserve path reopens empty
    board.cards.push(card);
    save();
    rerenderBoard(board.id);
    const bn = $('.board[data-id="' + board.id + '"]');
    const list = $('.cards', bn);
    list.scrollTop = list.scrollHeight;
    openComposer(bn, board); // stay open for rapid entry
  };
  addBtn.addEventListener('click', submit);
  descBtn.addEventListener('click', () => { desc.hidden = false; desc.focus(); });
  closeBtn.addEventListener('click', closeComposer);
  title.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); }
    if (e.key === 'Escape') closeComposer();
  });
  desc.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeComposer(); });
}
function autoGrow(ta) {
  const fit = () => { ta.style.height = 'auto'; ta.style.height = ta.scrollHeight + 'px'; };
  ta.addEventListener('input', fit);
  requestAnimationFrame(fit);
}

/* ---------- board rename ---------- */
function startBoardRename(boardNode, board, isNew) {
  const titleEl = $('.board-title', boardNode);
  const input = el('input', 'board-title-input');
  input.value = board.name;
  input.placeholder = 'Name this board';
  input.maxLength = 80;
  titleEl.replaceWith(input);
  input.focus();
  input.select();
  let committed = false;
  const commit = () => {
    if (committed) return;
    committed = true;
    const v = input.value.trim();
    if (v) board.name = v;
    else if (isNew) board.name = 'Untitled';
    save();
    rerenderBoard(board.id);
  };
  input.addEventListener('blur', commit);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
    if (e.key === 'Escape') { input.value = board.name || (isNew ? 'Untitled' : ''); input.blur(); }
  });
}

/* ---------- board menu ---------- */
function openBoardMenu(anchor, board) {
  openPopover(anchor, (pop, close) => {
    pop.appendChild(popItem('Rename board', ICONS.pencil, () => {
      close();
      const node = $('.board[data-id="' + board.id + '"]');
      startBoardRename(node, board, false);
    }));
    if (board.done.length) {
      pop.appendChild(popItem(board.showDone ? 'Hide completed' : 'Show completed (' + board.done.length + ')', ICONS.check, () => {
        close();
        board.showDone = !board.showDone;
        save();
        rerenderBoard(board.id);
      }));
    }
    pop.appendChild(popItem('Delete board', ICONS.trash, () => {
      close();
      const ws = activeWs();
      const idx = ws.boards.indexOf(board);
      ws.boards.splice(idx, 1);
      save();
      rerenderBoard(board.id);
      $('#hint').hidden = ws.boards.length > 0;
      undoableToast('Board deleted', () => ws.boards.splice(clamp(idx, 0, ws.boards.length), 0, board));
    }, 'danger'));
  });
}

/* ---------- file drag-in (attachments) ---------- */
(function fileDrops() {
  let dropCard = null;
  window.addEventListener('dragover', (e) => {
    if (!e.dataTransfer || !Array.from(e.dataTransfer.types).includes('Files')) return;
    e.preventDefault();
    const over = document.elementFromPoint(e.clientX, e.clientY);
    const cardNode = over && over.closest('.card:not(.done-card)');
    if (dropCard && dropCard !== cardNode) dropCard.classList.remove('drop-target');
    dropCard = cardNode || null;
    if (dropCard) {
      dropCard.classList.add('drop-target');
      e.dataTransfer.dropEffect = 'copy';
    } else {
      e.dataTransfer.dropEffect = 'none';
    }
  });
  window.addEventListener('dragleave', (e) => {
    if (e.relatedTarget === null && dropCard) { dropCard.classList.remove('drop-target'); dropCard = null; }
  });
  window.addEventListener('drop', async (e) => {
    e.preventDefault();
    const node = dropCard;
    if (dropCard) { dropCard.classList.remove('drop-target'); dropCard = null; }
    if (!node || !e.dataTransfer.files.length) return;
    const found = findCard(node.dataset.id);
    if (!found) return;
    const n = await addAttachmentsToCard(found.card, e.dataTransfer.files);
    if (n) {
      rerenderBoard(found.board.id);
      const openModal = $('.modal[data-card-id="' + found.card.id + '"]');
      if (openModal && typeof refreshModalAttachments === 'function') refreshModalAttachments(found.card);
      toast(n === 1 ? 'File attached' : n + ' files attached');
    }
  });
})();

/* ---------- canvas click delegation ---------- */
(function canvasClicks() {
  $('#canvas').addEventListener('click', (e) => {
    const boardNode = e.target.closest('.board');
    if (!boardNode) return;
    const board = findBoard(boardNode.dataset.id);
    if (!board) return;

    const circle = e.target.closest('.complete-circle');
    if (circle) {
      const cardNode = circle.closest('.card');
      if (circle.classList.contains('filled')) restoreCard(cardNode.dataset.id);
      else completeCard(cardNode.dataset.id);
      return;
    }
    const attBtn = e.target.closest('.att');
    if (attBtn) {
      const found = findCard(attBtn.closest('.card').dataset.id);
      const att = found && found.card.at.find(a => a.id === attBtn.dataset.attId);
      if (att) openAttachment(att);
      return;
    }
    if (e.target.closest('.add-card-btn')) { openComposer(boardNode, board); return; }
    if (e.target.closest('.board-menu-btn')) { openBoardMenu(e.target.closest('.board-menu-btn'), board); return; }
    const doneBar = e.target.closest('.done-bar');
    if (doneBar) {
      board.showDone = !board.showDone;
      save();
      rerenderBoard(board.id);
      return;
    }
    if (e.target.closest('.done-clear')) {
      const cleared = board.done.slice();
      board.done = [];
      board.showDone = false;
      save();
      rerenderBoard(board.id);
      undoableToast(cleared.length + ' completed cards cleared', () => { board.done = cleared.concat(board.done); });
      return;
    }
    const cardNode = e.target.closest('.card');
    if (cardNode && !cardNode.classList.contains('done-card') && !e.target.closest('button')) {
      openCardModal(cardNode.dataset.id);
      return;
    }
    if (cardNode && cardNode.classList.contains('done-card') && !e.target.closest('button')) {
      openCardModal(cardNode.dataset.id);
    }
  });

  $('#canvas').addEventListener('dblclick', (e) => {
    const titleEl = e.target.closest('.board-title');
    if (titleEl) {
      const boardNode = titleEl.closest('.board');
      startBoardRename(boardNode, findBoard(boardNode.dataset.id), false);
    }
  });
})();
