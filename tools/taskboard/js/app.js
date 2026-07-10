/* Slate — card modal, workspace switcher, settings, export/import, init */
'use strict';

/* ---------- card modal ---------- */
let refreshModalAttachments = null;

function openCardModal(cardId) {
  const found = findCard(cardId);
  if (!found) return;
  const { card, board } = found;
  const root = $('#modalRoot');
  root.textContent = '';

  const backdrop = el('div', 'modal-backdrop');
  const modal = el('div', 'modal' + (card.color ? ' tint-' + card.color : ''));
  modal.dataset.cardId = card.id;
  const accent = el('div', 'modal-accent');
  modal.appendChild(accent);
  const body = el('div', 'modal-body');
  modal.appendChild(body);

  /* title */
  const title = el('textarea', 'modal-title');
  title.rows = 1;
  title.value = card.t;
  title.placeholder = 'Card title';
  title.addEventListener('input', () => { card.t = title.value.trim() || card.t; save(); });
  title.addEventListener('blur', () => { if (!title.value.trim()) title.value = card.t; });
  body.appendChild(title);
  autoGrow(title);

  /* color row */
  const colorSec = section('Color');
  const swatches = el('div', 'swatches');
  const noneBtn = swatchBtn(null, card.color === null);
  swatches.appendChild(noneBtn);
  for (const cc of CARD_COLORS) swatches.appendChild(swatchBtn(cc, card.color === cc));
  colorSec.appendChild(swatches);
  body.appendChild(colorSec);

  function swatchBtn(cc, active) {
    const b = el('button', 'swatch' + (cc ? ' tint-' + cc : ' swatch-none') + (active ? ' active' : ''));
    b.title = cc ? COLOR_NAMES[cc] : 'No color';
    b.addEventListener('click', () => {
      card.color = cc;
      save();
      $$('.swatch', swatches).forEach(s => s.classList.remove('active'));
      b.classList.add('active');
      modal.className = 'modal' + (cc ? ' tint-' + cc : '');
    });
    return b;
  }

  /* due date */
  const dueSec = section('Due date');
  const dueRow = el('div', 'due-row');
  const dueInput = el('input');
  dueInput.type = 'date';
  dueInput.className = 'due-input';
  if (card.due) dueInput.value = card.due;
  dueInput.addEventListener('change', () => { card.due = dueInput.value || null; save(); });
  const dueClear = el('button', 'ghost-btn');
  dueClear.title = 'Clear date';
  dueClear.appendChild(svgIcon(ICONS.x, 12, 1.7));
  dueClear.addEventListener('click', () => { dueInput.value = ''; card.due = null; save(); });
  dueRow.append(dueInput, dueClear);
  dueSec.appendChild(dueRow);
  body.appendChild(dueSec);

  /* tags */
  const tagSec = section('Tags');
  const tagWrap = el('div', 'tag-edit');
  const chipRow = el('div', 'chip-row');
  const tagInput = el('input', 'tag-input');
  tagInput.placeholder = 'Add a tag…';
  tagInput.maxLength = 40;
  const sugRow = el('div', 'tag-suggestions');
  tagWrap.append(chipRow, tagInput, sugRow);
  tagSec.appendChild(tagWrap);
  body.appendChild(tagSec);

  function renderTagEditor() {
    chipRow.textContent = '';
    for (const t of card.tags) {
      const chip = el('span', 'chip tag-chip tint-' + tagColor(t), t);
      const rm = el('button', 'chip-x');
      rm.setAttribute('aria-label', 'Remove tag ' + t);
      rm.appendChild(svgIcon(ICONS.x, 9, 2));
      rm.addEventListener('click', () => { card.tags = card.tags.filter(x => x !== t); save(); renderTagEditor(); });
      chip.appendChild(rm);
      chipRow.appendChild(chip);
    }
    sugRow.textContent = '';
    const q = tagInput.value.trim().toLowerCase();
    const existing = collectWsTags().filter(t => !card.tags.includes(t) && (!q || t.toLowerCase().includes(q)));
    for (const t of existing.slice(0, 6)) {
      const s = el('button', 'chip tag-chip suggestion tint-' + tagColor(t), t);
      s.addEventListener('click', () => { addTag(t); });
      sugRow.appendChild(s);
    }
  }
  function addTag(t) {
    t = t.trim().replace(/,+$/, '');
    if (!t || card.tags.includes(t)) { tagInput.value = ''; renderTagEditor(); return; }
    card.tags.push(t);
    save();
    tagInput.value = '';
    renderTagEditor();
    tagInput.focus();
  }
  tagInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); addTag(tagInput.value); }
    else if (e.key === 'Backspace' && !tagInput.value && card.tags.length) {
      card.tags.pop(); save(); renderTagEditor();
    }
  });
  tagInput.addEventListener('input', renderTagEditor);
  renderTagEditor();

  /* description */
  const descSec = section('Description');
  const desc = el('textarea', 'modal-desc');
  desc.rows = 3;
  desc.placeholder = 'Add a description…';
  desc.value = card.d || '';
  desc.addEventListener('input', () => { card.d = desc.value; save(); });
  descSec.appendChild(desc);
  body.appendChild(descSec);
  autoGrow(desc);

  /* attachments */
  const attSec = section('Attachments');
  const attGrid = el('div', 'att-grid');
  const attActions = el('div', 'att-actions');
  const browse = el('button', 'ghost-btn att-browse');
  browse.appendChild(svgIcon(ICONS.upload, 13, 1.6));
  browse.appendChild(el('span', null, 'Add files'));
  const hiddenInput = el('input');
  hiddenInput.type = 'file';
  hiddenInput.multiple = true;
  hiddenInput.hidden = true;
  browse.addEventListener('click', () => hiddenInput.click());
  hiddenInput.addEventListener('change', async () => {
    const n = await addAttachmentsToCard(card, hiddenInput.files);
    hiddenInput.value = '';
    if (n) { renderAttGrid(); rerenderBoard(board.id); }
  });
  attActions.append(browse, el('span', 'att-hint', 'or drop files anywhere on this card'));
  attSec.append(attGrid, attActions, hiddenInput);
  body.appendChild(attSec);

  function renderAttGrid() {
    attGrid.textContent = '';
    for (const a of card.at) {
      const tile = el('div', 'att-tile');
      const open = el('button', 'att-tile-open');
      open.title = a.name;
      if (a.thumb) {
        const img = el('img');
        img.src = a.thumb;
        img.alt = a.name;
        open.appendChild(img);
      } else {
        open.classList.add('att-tile-file');
        open.appendChild(svgIcon(ICONS.file, 18, 1.3));
        open.appendChild(el('span', 'att-tile-ext', extOf(a.name)));
      }
      open.addEventListener('click', () => openAttachment(a));
      const label = el('div', 'att-tile-name', a.name);
      label.title = a.name + ' · ' + fmtSize(a.size);
      const rm = el('button', 'att-tile-x');
      rm.title = 'Remove attachment';
      rm.appendChild(svgIcon(ICONS.x, 10, 2));
      rm.addEventListener('click', () => {
        card.at = card.at.filter(x => x.id !== a.id);
        fileDel(a.id);
        save();
        renderAttGrid();
        rerenderBoard(board.id);
      });
      tile.append(open, label, rm);
      attGrid.appendChild(tile);
    }
    attGrid.hidden = !card.at.length;
  }
  renderAttGrid();
  refreshModalAttachments = (c) => { if (c.id === card.id) renderAttGrid(); };

  /* footer */
  const foot = el('div', 'modal-foot');
  const completeBtn = el('button', 'primary-btn complete-btn');
  const isDone = found.done;
  completeBtn.appendChild(svgIcon(ICONS.check, 13, 2));
  completeBtn.appendChild(el('span', null, isDone ? 'Restore' : 'Complete'));
  completeBtn.addEventListener('click', () => {
    closeModal();
    if (isDone) restoreCard(card.id);
    else completeCard(card.id);
  });
  const created = el('span', 'modal-stamp', 'Created ' + new Date(card.created).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }));
  const del = el('button', 'ghost-btn danger');
  del.appendChild(svgIcon(ICONS.trash, 13, 1.5));
  del.appendChild(el('span', null, 'Delete'));
  del.addEventListener('click', () => {
    closeModal();
    const arr = isDone ? board.done : board.cards;
    const idx = arr.indexOf(card);
    if (idx >= 0) arr.splice(idx, 1);
    save();
    rerenderBoard(board.id);
    undoableToast('Card deleted', () => arr.splice(clamp(idx, 0, arr.length), 0, card));
  });
  foot.append(completeBtn, created, del);
  modal.appendChild(foot);

  function section(label) {
    const s = el('div', 'modal-section');
    s.appendChild(el('div', 'modal-label', label));
    return s;
  }

  /* the modal is itself a drop zone — the window-level handler can't see through the backdrop */
  modal.addEventListener('dragover', (e) => {
    if (!e.dataTransfer || !Array.from(e.dataTransfer.types).includes('Files')) return;
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = 'copy';
    modal.classList.add('drop-target');
  });
  modal.addEventListener('dragleave', (e) => {
    if (!modal.contains(e.relatedTarget)) modal.classList.remove('drop-target');
  });
  modal.addEventListener('drop', async (e) => {
    e.preventDefault();
    e.stopPropagation();
    modal.classList.remove('drop-target');
    if (!e.dataTransfer.files.length) return;
    const n = await addAttachmentsToCard(card, e.dataTransfer.files);
    if (n) {
      renderAttGrid();
      rerenderBoard(board.id);
      toast(n === 1 ? 'File attached' : n + ' files attached');
    }
  });

  backdrop.appendChild(modal);
  root.appendChild(backdrop);
  requestAnimationFrame(() => backdrop.classList.add('show'));

  let closed = false;
  function closeModal() {
    if (closed) return;
    closed = true;
    refreshModalAttachments = null;
    backdrop.classList.remove('show');
    setTimeout(() => backdrop.remove(), 180);
    window.removeEventListener('keydown', onKey);
    if (!card.t) card.t = 'Untitled';
    save.flush();
    rerenderBoard(board.id);
  }
  backdrop.addEventListener('mousedown', (e) => { if (e.target === backdrop) closeModal(); });
  function onKey(e) {
    if (e.key === 'Escape' && !activePopoverClose && !$('#lightboxRoot .lightbox')) closeModal();
  }
  window.addEventListener('keydown', onKey);
  title.focus();
  title.setSelectionRange(title.value.length, title.value.length);
}

function collectWsTags() {
  const set = new Set();
  for (const b of activeWs().boards) {
    for (const c of b.cards) c.tags.forEach(t => set.add(t));
    for (const c of b.done) c.tags.forEach(t => set.add(t));
  }
  return Array.from(set).sort((a, b) => a.localeCompare(b));
}

/* ---------- workspace switcher ---------- */
function openWsSwitcher() {
  const anchor = $('#wsSwitcher');
  openPopover(anchor, (pop, close) => {
    pop.classList.add('ws-pop');
    for (const w of state.ws) {
      const row = el('div', 'ws-row' + (w.id === state.activeWs ? ' active' : ''));
      const name = el('button', 'ws-row-name');
      name.appendChild(el('span', null, w.name));
      name.appendChild(el('span', 'ws-row-count', w.boards.length + (w.boards.length === 1 ? ' board' : ' boards')));
      name.addEventListener('click', () => {
        state.activeWs = w.id;
        save();
        close();
        renderAll();
      });
      const rename = el('button', 'ghost-btn ws-row-btn');
      rename.title = 'Rename workspace';
      rename.appendChild(svgIcon(ICONS.pencil, 12, 1.6));
      rename.addEventListener('click', (e) => {
        e.stopPropagation();
        inlineRename(row, w);
      });
      const trash = el('button', 'ghost-btn ws-row-btn danger');
      trash.title = 'Delete workspace';
      trash.appendChild(svgIcon(ICONS.trash, 12, 1.5));
      trash.addEventListener('click', (e) => {
        e.stopPropagation();
        const idx = state.ws.indexOf(w);
        state.ws.splice(idx, 1);
        if (!state.ws.length) state.ws.push(newWorkspace('Personal'));
        if (state.activeWs === w.id) state.activeWs = state.ws[Math.max(0, idx - 1)].id;
        save();
        close();
        renderAll();
        undoableToast('Workspace "' + w.name + '" deleted', () => {
          state.ws.splice(clamp(idx, 0, state.ws.length), 0, w);
          state.activeWs = w.id;
        });
      });
      row.append(name, rename, trash);
      pop.appendChild(row);
    }
    const divider = el('div', 'pop-divider');
    pop.appendChild(divider);
    const add = popItem('New workspace', ICONS.plus, () => {
      const w = newWorkspace('New space');
      state.ws.push(w);
      state.activeWs = w.id;
      save();
      close();
      renderAll();
      openWsSwitcher(); // reopen so they can rename it immediately
      setTimeout(() => {
        const rows = $$('.ws-row');
        const row = rows[rows.length - 1];
        if (row) inlineRename(row, w);
      }, 30);
    });
    pop.appendChild(add);

    function inlineRename(row, w) {
      const input = el('input', 'ws-rename-input');
      input.value = w.name;
      input.maxLength = 60;
      row.textContent = '';
      row.appendChild(input);
      input.focus();
      input.select();
      let done = false;
      const commit = () => {
        if (done) return;
        done = true;
        const v = input.value.trim();
        if (v) w.name = v;
        save();
        close();
        renderTopbar();
        openWsSwitcher();
      };
      input.addEventListener('blur', commit);
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') input.blur();
        if (e.key === 'Escape') { input.value = w.name; input.blur(); }
      });
    }
  });
}

/* ---------- settings ---------- */
async function exportBackup() {
  const files = await fileAll();
  const payload = { app: 'slate', v: 1, exported: new Date().toISOString(), state: state, files: files };
  const blob = new Blob([JSON.stringify(payload)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'slate-backup-' + todayISO() + '.json';
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 10000);
  toast('Backup exported');
}

function openSettings() {
  openPopover($('#settingsBtn'), (pop, close) => {
    pop.appendChild(popItem('Export backup', ICONS.download, () => {
      close();
      exportBackup();
    }));
    pop.appendChild(popItem('Import backup', ICONS.upload, () => {
      close();
      const input = el('input');
      input.type = 'file';
      input.accept = 'application/json,.json';
      input.hidden = true;
      document.body.appendChild(input);
      input.addEventListener('change', async () => {
        try {
          const text = await input.files[0].text();
          const payload = JSON.parse(text);
          const st = payload && payload.app === 'slate' ? payload.state : null;
          const valid = st && st.v === 1 && Array.isArray(st.ws) && st.ws.length &&
            st.ws.every(w => w && Array.isArray(w.boards) &&
              w.boards.every(b => b && Array.isArray(b.cards) && Array.isArray(b.done)));
          if (!valid) {
            toast('Not a Slate backup file', { tone: 'danger' });
            return;
          }
          const prev = JSON.parse(JSON.stringify(state));
          for (const [id, dataUrl] of Object.entries(payload.files || {})) await filePut(id, dataUrl);
          state = migrateState(st); // normalizes shape so renderers can't throw on a crafted payload
          saveNow();
          // register the undo BEFORE rendering — even if a render fails, the restore path exists
          undoableToast('Backup imported — replaced ' + prev.ws.length +
            (prev.ws.length === 1 ? ' workspace' : ' workspaces'), () => { state = prev; });
          renderAll();
        } catch (e) {
          console.error(e);
          toast('Could not read that file', { tone: 'danger' });
        } finally {
          input.remove();
        }
      });
      input.click();
    }));
    const divider = el('div', 'pop-divider');
    pop.appendChild(divider);
    const note = el('div', 'pop-note', 'Everything lives in this browser. Export a backup now and then.');
    pop.appendChild(note);
  });
}

/* ---------- init ---------- */
(function init() {
  state = loadState();
  renderAll();
  $('#wsSwitcher').addEventListener('click', openWsSwitcher);
  $('#settingsBtn').addEventListener('click', openSettings);
  $$('#viewSeg .seg-btn').forEach(b => b.addEventListener('click', () => {
    if ((state.view || 'tasks') === b.dataset.view) return;
    state.view = b.dataset.view;
    save();
    renderAll();
  }));
  $$('#brainTabs .seg-btn').forEach(b => b.addEventListener('click', () => {
    if (brainTab === b.dataset.tab) return;
    brainTab = b.dataset.tab;
    renderAll();
  }));
  $('#themeBtn').addEventListener('click', () => {
    state.theme = state.theme === 'dark' ? 'light' : 'dark';
    save();
    applyTheme();
  });
  $('#tidyBtn').addEventListener('click', tidyBoards);
  setTimeout(gcAttachments, 4000); // sweep orphaned attachment blobs off the interaction path
  if (recoveryKey) {
    toast('Saved data could not be read — a copy was kept at localStorage["' + recoveryKey + '"]',
      { tone: 'danger', ms: 12000 });
  }
})();
