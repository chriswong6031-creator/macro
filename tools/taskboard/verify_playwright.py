#!/usr/bin/env python3
"""End-to-end verification of Slate against a local server.

Usage: python3 -m playwright... just run: python3 verify_playwright.py [base_url]
Writes screenshots to /tmp/slate_verify/.
"""
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8123"
SHOTS = Path("/tmp/slate_verify")
SHOTS.mkdir(exist_ok=True)

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))


def drag(page, from_box, to_x, to_y, steps=12):
    page.mouse.move(from_box["x"] + from_box["width"] / 2, from_box["y"] + 14)
    page.mouse.down()
    fx, fy = from_box["x"] + from_box["width"] / 2, from_box["y"] + 14
    for i in range(1, steps + 1):
        page.mouse.move(fx + (to_x - fx) * i / steps, fy + (to_y - fy) * i / steps)
        page.wait_for_timeout(16)
    page.mouse.up()
    page.wait_for_timeout(350)


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.goto(BASE)
    page.wait_for_timeout(400)

    # 1. first-run seed
    check("first-run: 3 seeded boards", page.locator(".board").count() == 3)
    check("first-run: 7 seeded cards", page.locator(".card").count() == 7,
          str(page.locator(".card").count()))
    page.screenshot(path=str(SHOTS / "01_first_run.png"))

    # 2. add card via composer (Enter for rapid entry)
    b0 = page.locator(".board").nth(0)
    b0.locator(".add-card-btn").click()
    page.locator(".composer-title").fill("Buy espresso beans")
    page.keyboard.press("Enter")
    page.wait_for_timeout(200)
    check("composer: card added", b0.locator(".card-title", has_text="Buy espresso beans").count() == 1)
    check("composer: stays open for rapid entry", page.locator(".composer-title").count() == 1)
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    check("composer: Escape closes", page.locator(".composer").count() == 0)

    # 3. drag card from board 1 to board 2
    src = b0.locator(".card", has_text="Drag me onto another board")
    sbox = src.bounding_box()
    b1 = page.locator(".board").nth(1)
    tbox = b1.locator(".cards").bounding_box()
    drag(page, sbox, tbox["x"] + tbox["width"] / 2, tbox["y"] + tbox["height"] - 10)
    moved = b1.locator(".card-title", has_text="Drag me onto another board").count()
    check("card dnd: moved across boards", moved == 1)
    check("card dnd: removed from source",
          b0.locator(".card-title", has_text="Drag me onto another board").count() == 0)

    # 4. complete ritual
    target = b0.locator(".card", has_text="Click my circle")
    target.locator(".complete-circle").click()
    page.wait_for_timeout(1100)
    check("complete: card left active list", b0.locator(".card", has_text="Click my circle").count() == 0)
    check("complete: done ledger shows", "1 done" in (b0.locator(".done-bar-label").text_content() or ""))
    # expand + restore
    b0 = page.locator(".board").nth(0)
    b0.locator(".done-bar").click()
    page.wait_for_timeout(250)
    check("done: expanded list", page.locator(".done-list .done-card").count() == 1)
    page.locator(".done-card .complete-circle.filled").click()
    page.wait_for_timeout(300)
    b0 = page.locator(".board").nth(0)
    check("done: restore works", b0.locator(".card", has_text="Click my circle").count() == 1)
    # complete again for the screenshots/state
    b0.locator(".card", has_text="Click my circle").locator(".complete-circle").click()
    page.wait_for_timeout(1100)

    # 5. card modal: color, tag, due, desc
    page.locator(".card", has_text="Buy espresso beans").click()
    page.wait_for_timeout(350)
    check("modal: opens", page.locator(".modal").count() == 1)
    page.locator(".swatch.tint-c7").click()
    page.locator(".tag-input").fill("errand")
    page.keyboard.press("Enter")
    page.locator(".due-input").fill("2026-07-15")
    page.locator(".modal-desc").fill("The good ones from the roastery on 5th.")
    page.wait_for_timeout(200)
    page.screenshot(path=str(SHOTS / "02_modal.png"))
    page.mouse.click(30, 450)  # backdrop
    page.wait_for_timeout(350)
    check("modal: closes on outside click", page.locator(".modal").count() == 0)
    card = page.locator(".card", has_text="Buy espresso beans")
    check("modal edits: tint applied", "tint-c7" in (card.get_attribute("class") or ""))
    check("modal edits: tag chip", card.locator(".tag-chip", has_text="errand").count() == 1)
    check("modal edits: due chip", card.locator(".due-chip").count() == 1)
    check("modal edits: desc indicator", card.locator(".desc-chip").count() == 1)

    # 6. attachment via simulated file drop (image)
    card_box = card.bounding_box()
    page.evaluate(
        """async ([cx, cy]) => {
            const cv = document.createElement('canvas');
            cv.width = 80; cv.height = 60;
            const ctx = cv.getContext('2d');
            ctx.fillStyle = '#3A5BF0'; ctx.fillRect(0,0,80,60);
            ctx.fillStyle = '#fff'; ctx.fillRect(16,14,48,32);
            const blob = await new Promise(r => cv.toBlob(r, 'image/png'));
            const file = new File([blob], 'mock-photo.png', {type: 'image/png'});
            const dt = new DataTransfer();
            dt.items.add(file);
            const txt = new File([new Blob(['hello slate'])], 'notes.txt', {type: 'text/plain'});
            dt.items.add(txt);
            window.dispatchEvent(new DragEvent('dragover', {dataTransfer: dt, clientX: cx, clientY: cy, cancelable: true, bubbles: true}));
            window.dispatchEvent(new DragEvent('drop', {dataTransfer: dt, clientX: cx, clientY: cy, cancelable: true, bubbles: true}));
        }""",
        [card_box["x"] + card_box["width"] / 2, card_box["y"] + 10],
    )
    page.wait_for_timeout(900)
    card = page.locator(".card", has_text="Buy espresso beans")
    check("attach: image thumbnail on card", card.locator(".att-img img").count() == 1)
    check("attach: file chip on card", card.locator(".att-file").count() == 1)
    chip_title = card.locator(".att-file").get_attribute("title")
    check("attach: hover shows filename", chip_title == "notes.txt", str(chip_title))
    # lightbox
    card.locator(".att-img").click()
    page.wait_for_timeout(350)
    check("attach: lightbox opens", page.locator(".lightbox img").count() == 1)
    page.screenshot(path=str(SHOTS / "03_lightbox.png"))
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    check("attach: lightbox closes", page.locator(".lightbox").count() == 0)

    # 7. double-click canvas creates a board
    page.mouse.dblclick(700, 700)
    page.wait_for_timeout(300)
    check("dblclick: new board input", page.locator(".board-title-input").count() == 1)
    page.keyboard.type("Errands")
    page.keyboard.press("Enter")
    page.wait_for_timeout(250)
    check("dblclick: board named", page.locator(".board-title", has_text="Errands").count() == 1)
    check("dblclick: 4 boards now", page.locator(".board").count() == 4)

    # 8. board drag persists
    eb = page.locator(".board", has=page.locator(".board-title", has_text="Errands"))
    ebox = eb.bounding_box()
    drag(page, ebox, ebox["x"] + 260, ebox["y"] + 60)
    pos_before = eb.evaluate("n => [n.style.left, n.style.top]")
    page.reload()
    page.wait_for_timeout(500)
    eb = page.locator(".board", has=page.locator(".board-title", has_text="Errands"))
    pos_after = eb.evaluate("n => [n.style.left, n.style.top]")
    check("board drag: position persisted across reload", pos_before == pos_after,
          f"{pos_before} vs {pos_after}")

    # 9. persistence of everything else
    check("persist: cards survive reload",
          page.locator(".card-title", has_text="Buy espresso beans").count() == 1)
    check("persist: attachments survive reload",
          page.locator(".card", has_text="Buy espresso beans").locator(".att-img img").count() == 1)
    check("persist: done ledger survives", "1 done" in (page.locator(".done-bar-label").first.text_content() or ""))

    # 10. tidy
    page.locator("#tidyBtn").click()
    page.wait_for_timeout(700)
    xs = page.eval_on_selector_all(".board", "ns => ns.map(n => parseInt(n.style.left))")
    ys = page.eval_on_selector_all(".board", "ns => ns.map(n => parseInt(n.style.top))")
    on_grid = all((x - 48) % 324 == 0 for x in xs)
    check("tidy: boards snapped to grid columns", on_grid, f"xs={xs} ys={ys}")
    page.screenshot(path=str(SHOTS / "04_tidy_light.png"))

    # 11. workspaces: create, switch, rename flow
    page.locator("#wsSwitcher").click()
    page.wait_for_timeout(250)
    page.locator(".pop-item", has_text="New workspace").click()
    page.wait_for_timeout(400)
    if page.locator(".ws-rename-input").count():
        page.locator(".ws-rename-input").fill("Trading")
        page.keyboard.press("Enter")
        page.wait_for_timeout(300)
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    check("workspace: created + switched", (page.locator("#wsName").text_content() or "") == "Trading",
          page.locator("#wsName").text_content())
    check("workspace: empty canvas hint", page.locator("#hint").is_visible())
    # add a board here, then switch back
    page.mouse.dblclick(500, 400)
    page.keyboard.type("Watchlist")
    page.keyboard.press("Enter")
    page.wait_for_timeout(200)
    page.locator("#wsSwitcher").click()
    page.wait_for_timeout(250)
    page.locator(".ws-row-name", has_text="Personal").click()
    page.wait_for_timeout(300)
    check("workspace: switch back shows 4 boards", page.locator(".board").count() == 4)

    # 12. dark theme
    page.locator("#themeBtn").click()
    page.wait_for_timeout(300)
    check("theme: dark applied", page.evaluate("document.documentElement.dataset.theme") == "dark")
    page.screenshot(path=str(SHOTS / "05_dark.png"))
    page.locator("#themeBtn").click()

    # 13. export payload sanity
    n_files = page.evaluate("async () => Object.keys(await fileAll()).length")
    check("export: attachment store has files", n_files >= 2, str(n_files))
    state_ok = page.evaluate(
        "() => { const s = JSON.parse(localStorage.getItem('slate.state.v1')); return s.v === 1 && s.ws.length === 2; }")
    check("export: state JSON valid, 2 workspaces", state_ok)

    # 14. delete card with undo
    page.locator(".card", has_text="Buy espresso beans").click()
    page.wait_for_timeout(300)
    page.locator(".modal-foot .ghost-btn.danger").click()
    page.wait_for_timeout(300)
    check("delete: card gone", page.locator(".card", has_text="Buy espresso beans").count() == 0)
    check("delete: undo toast", page.locator(".toast-action", has_text="Undo").count() == 1)
    page.locator(".toast-action").click()
    page.wait_for_timeout(300)
    check("delete: undo restores", page.locator(".card", has_text="Buy espresso beans").count() == 1)

    # --- BRAIN ---
    page.locator("#viewSeg .seg-btn[data-view='brain']").click()
    page.wait_for_timeout(350)
    check("brain: capture hint shown", page.locator("#hint").is_visible()
          and "learned" in (page.locator("#hint").text_content() or ""))
    check("brain: workspace controls hidden", not page.locator("#wsSwitcher").is_visible()
          and not page.locator("#tidyBtn").is_visible())
    check("brain: tabs + fab visible", page.locator("#brainTabs").is_visible()
          and page.locator("#fabCapture").is_visible())

    # capture a note into a NEW topic via double-click
    page.mouse.dblclick(620, 420)
    page.wait_for_timeout(250)
    check("brain: composer opens on dblclick", page.locator(".bnote.composing").count() == 1)
    page.locator(".bnote-input").fill("Trends persist longer than you expect")
    page.locator(".bnote-newtopic").fill("Markets")
    page.locator(".bnote-actions .primary-btn").click()
    page.wait_for_timeout(400)
    saved_card = page.locator(".bnote", has_text="Trends persist")
    check("brain: note card stays on board", saved_card.count() == 1)
    check("brain: card shows Saved + topic chip",
          saved_card.locator(".bnote-saved").count() == 1
          and saved_card.locator(".tag-chip", has_text="Markets").count() == 1)
    n_markets = page.evaluate(
        "() => (state.brain.categories.find(c => c.name === 'Markets') || {notes: []}).notes.length")
    check("brain: note persisted into topic instantly", n_markets == 1, str(n_markets))

    # second note, filed under the EXISTING topic chip
    page.mouse.dblclick(980, 480)
    page.wait_for_timeout(250)
    page.locator(".bnote-input").fill("Position size beats entry timing")
    page.locator(".bnote.composing .topic-chip", has_text="Markets").click()
    page.locator(".bnote-actions .primary-btn").click()
    page.wait_for_timeout(400)
    n_markets = page.evaluate(
        "() => state.brain.categories.find(c => c.name === 'Markets').notes.length")
    check("brain: existing-topic filing works", n_markets == 2, str(n_markets))
    page.screenshot(path=str(SHOTS / "07_brain_capture.png"))

    # library view: panes per topic
    page.locator("#brainTabs .seg-btn[data-tab='library']").click()
    page.wait_for_timeout(350)
    mpane = page.locator(".pane", has=page.locator(".pane-title", has_text="Markets"))
    check("brain library: Markets pane with 2 notes", mpane.locator(".pnote").count() == 2)
    check("brain library: seeded pane present",
          page.locator(".pane-title", has_text="How this works").count() == 1)
    page.screenshot(path=str(SHOTS / "08_brain_library.png"))

    # edit a note from the library
    mpane.locator(".pnote", has_text="Position size").click()
    page.wait_for_timeout(300)
    page.locator(".bnote-edit").fill("Position size beats entry timing — always.")
    page.mouse.click(30, 500)
    page.wait_for_timeout(350)
    check("brain: note edit saves",
          page.locator(".pnote", has_text="always.").count() == 1)

    # shadow-push semantics: reload wipes the capture board, library keeps everything
    page.reload()
    page.wait_for_timeout(500)
    check("brain: view persists across reload",
          page.evaluate("document.body.dataset.view") == "brain")
    check("brain: capture board wiped on reload",
          page.locator(".bnote").count() == 0 and page.locator("#hint").is_visible())
    page.locator("#brainTabs .seg-btn[data-tab='library']").click()
    page.wait_for_timeout(300)
    check("brain: library retains notes after reload",
          page.locator(".pane", has=page.locator(".pane-title", has_text="Markets")).locator(".pnote").count() == 2)

    # delete note + undo
    page.locator(".pnote", has_text="Trends persist").click()
    page.wait_for_timeout(300)
    page.locator(".modal-foot .ghost-btn.danger").click()
    page.wait_for_timeout(300)
    check("brain: note deleted", page.locator(".pnote", has_text="Trends persist").count() == 0)
    page.locator(".toast-action").click()
    page.wait_for_timeout(300)
    check("brain: delete undo restores", page.locator(".pnote", has_text="Trends persist").count() == 1)

    # delete-undo from a live capture card restores the card too (review finding)
    page.locator("#brainTabs .seg-btn[data-tab='board']").click()
    page.wait_for_timeout(300)
    page.mouse.dblclick(700, 500)
    page.wait_for_timeout(250)
    page.locator(".bnote-input").fill("Ephemeral card, durable note")
    page.locator(".bnote.composing .topic-chip", has_text="Markets").click()
    page.locator(".bnote-actions .primary-btn").click()
    page.wait_for_timeout(400)
    page.locator(".bnote", has_text="Ephemeral card").click()
    page.wait_for_timeout(300)
    page.locator(".modal-foot .ghost-btn.danger").click()
    page.wait_for_timeout(300)
    check("brain: delete removes capture card", page.locator(".bnote", has_text="Ephemeral card").count() == 0)
    page.locator(".toast-action").click()
    page.wait_for_timeout(300)
    check("brain: undo restores capture card too", page.locator(".bnote", has_text="Ephemeral card").count() == 1)

    # duplicate topic rename is blocked (review finding)
    page.locator("#brainTabs .seg-btn[data-tab='library']").click()
    page.wait_for_timeout(300)
    page.locator(".pane", has=page.locator(".pane-title", has_text="Markets")).locator(".pane-title").dblclick()
    page.wait_for_timeout(200)
    page.locator(".board-title-input").fill("How this works")
    page.keyboard.press("Enter")
    page.wait_for_timeout(300)
    check("brain: duplicate topic rename blocked",
          page.locator(".pane-title", has_text="Markets").count() == 1
          and page.locator(".toast-danger").count() == 1)

    # --- COMMAND PALETTE ---
    page.keyboard.press("Control+k")
    page.wait_for_timeout(250)
    check("palette: opens on ctrl+k", page.locator(".palette").count() == 1)
    check("palette: quick actions on empty query",
          page.locator(".palette-group", has_text="Actions").count() == 1)
    page.locator(".palette-input").fill("espresso")
    page.wait_for_timeout(200)
    check("palette: finds card across views",
          page.locator(".palette-row", has_text="Buy espresso beans").count() == 1)
    page.keyboard.press("Enter")
    page.wait_for_timeout(600)
    check("palette: opens card in boards view",
          page.evaluate("document.body.dataset.view") == "tasks"
          and page.locator(".modal-title").count() == 1
          and page.locator(".modal-title").input_value() == "Buy espresso beans")
    page.mouse.click(30, 550)
    page.wait_for_timeout(300)
    page.locator("#searchBtn").click()
    page.wait_for_timeout(250)
    check("palette: search button opens it", page.locator(".palette").count() == 1)
    page.locator(".palette-input").fill("trends persist")
    page.wait_for_timeout(200)
    page.keyboard.press("Enter")
    page.wait_for_timeout(700)
    check("palette: opens note in library",
          page.evaluate("document.body.dataset.view") == "brain"
          and page.locator(".bnote-edit").count() == 1
          and "Trends persist" in page.locator(".bnote-edit").input_value())
    page.mouse.click(30, 600)
    page.wait_for_timeout(300)
    page.keyboard.press("Control+k")
    page.wait_for_timeout(200)
    page.locator(".palette-input").fill("dark")
    page.wait_for_timeout(200)
    page.keyboard.press("Enter")
    page.wait_for_timeout(250)
    check("palette: action runs (toggle theme)",
          page.evaluate("document.documentElement.dataset.theme") == "dark")
    page.locator("#themeBtn").click()
    page.wait_for_timeout(200)

    # back to tasks for the remaining regressions
    page.locator("#viewSeg .seg-btn[data-view='tasks']").click()
    page.wait_for_timeout(300)
    check("brain: switch back to boards", page.locator(".board").count() == 4)

    # 15. REGRESSION: composer draft survives a board re-render (review finding: input loss)
    b0 = page.locator(".board").nth(0)
    b0.locator(".add-card-btn").click()
    page.locator(".composer-title").fill("half-typed thought")
    page.evaluate("rerenderBoard(activeWs().boards[0].id)")
    page.wait_for_timeout(250)
    check("regression: composer draft survives rerender",
          page.locator(".composer-title").input_value() == "half-typed thought")
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)

    # 16. REGRESSION: double-complete across a mid-ritual rerender cannot duplicate into done
    dup = page.evaluate(
        """async () => {
            const b = activeWs().boards.find(x => x.cards.length);
            const c = b.cards[0];
            completeCard(c.id);
            await new Promise(r => setTimeout(r, 100));
            rerenderBoard(b.id);           // wipes the .completing DOM class mid-ritual
            completeCard(c.id);            // second click on the fresh node
            await new Promise(r => setTimeout(r, 1400));
            return { inDone: b.done.filter(x => x.id === c.id).length,
                     inCards: b.cards.filter(x => x.id === c.id).length };
        }""")
    check("regression: no duplicate in done", dup["inDone"] == 1 and dup["inCards"] == 0, str(dup))

    # 17. REGRESSION: dropping a file on the OPEN modal attaches it
    page.locator(".card", has_text="Buy espresso beans").click()
    page.wait_for_timeout(300)
    tiles_before = page.locator(".att-tile").count()
    page.evaluate(
        """() => {
            const m = document.querySelector('.modal');
            const r = m.getBoundingClientRect();
            const dt = new DataTransfer();
            dt.items.add(new File([new Blob(['modal drop'])], 'dropped-on-modal.txt', {type: 'text/plain'}));
            const opts = {dataTransfer: dt, clientX: r.left + r.width/2, clientY: r.top + 40, cancelable: true, bubbles: true};
            m.dispatchEvent(new DragEvent('dragover', opts));
            m.dispatchEvent(new DragEvent('drop', opts));
        }""")
    page.wait_for_timeout(600)
    check("regression: modal drop attaches file", page.locator(".att-tile").count() == tiles_before + 1,
          f"{tiles_before} -> {page.locator('.att-tile').count()}")
    page.mouse.click(30, 450)
    page.wait_for_timeout(300)

    # 18. REGRESSION: an .html attachment downloads instead of rendering (script-execution vector)
    card = page.locator(".card", has_text="Buy espresso beans")
    cb = card.bounding_box()
    page.evaluate(
        """([cx, cy]) => {
            const dt = new DataTransfer();
            dt.items.add(new File([new Blob(['<script>document.title="pwned"</script>'])], 'evil.html', {type: 'text/html'}));
            const opts = {dataTransfer: dt, clientX: cx, clientY: cy, cancelable: true, bubbles: true};
            window.dispatchEvent(new DragEvent('dragover', opts));
            window.dispatchEvent(new DragEvent('drop', opts));
        }""", [cb["x"] + cb["width"] / 2, cb["y"] + 10])
    page.wait_for_timeout(600)
    card = page.locator(".card", has_text="Buy espresso beans")
    html_chip = card.locator(".att-file[title='evil.html']")
    check("regression: html file shows as chip", html_chip.count() == 1)
    with page.expect_download() as dl:
        html_chip.click()
    check("regression: html attachment downloads (not rendered)",
          dl.value.suggested_filename == "evil.html", dl.value.suggested_filename)
    check("regression: no script execution", "pwned" not in page.title(), page.title())

    page.screenshot(path=str(SHOTS / "06_final.png"))

    # --- PWA (served modular app only: the single-file build strips SW/manifest) ---
    if BASE.startswith("http") and not BASE.endswith(".html"):
        reg = page.evaluate(
            "async () => { const r = await navigator.serviceWorker.getRegistration();"
            " return !!(r && (r.active || r.installing || r.waiting)); }")
        check("pwa: service worker registered", reg)
        check("pwa: manifest served",
              page.evaluate("async () => (await fetch('manifest.webmanifest')).status") == 200)
        check("pwa: icons served",
              page.evaluate("async () => (await fetch('icons/icon-192.png')).status") == 200)
        tc = page.evaluate("document.querySelector('meta[name=\"theme-color\"]').content")
        check("pwa: theme-color meta synced", tc in ("#F5F6F8", "#0F1216"), str(tc))

    # --- RESPONSIVE SMOKE (phone viewport, fresh context) ---
    ctx3 = browser.new_context(viewport={"width": 390, "height": 844},
                               has_touch=True, is_mobile=True)
    p3 = ctx3.new_page()
    p3.goto(BASE)
    p3.wait_for_timeout(500)
    fits = p3.evaluate("() => document.querySelector('#topbar').scrollWidth <= window.innerWidth + 1")
    check("mobile: topbar fits viewport", fits)
    check("mobile: boards render", p3.locator(".board").count() == 3)
    p3.locator(".card", has_text="Plan the week").click()
    p3.wait_for_timeout(400)
    mb = p3.locator(".modal").bounding_box()
    check("mobile: modal is a full-width sheet", mb is not None and abs(mb["width"] - 390) < 2
          and mb["y"] + mb["height"] >= 842, str(mb))
    p3.screenshot(path=str(SHOTS / "09_mobile_sheet.png"))
    p3.mouse.click(195, 10)
    p3.wait_for_timeout(300)
    p3.locator("#viewSeg .seg-btn[data-view='brain']").click()
    p3.wait_for_timeout(300)
    check("mobile: brain fab visible", p3.locator("#fabCapture").is_visible())
    p3.locator("#fabCapture").click()
    p3.wait_for_timeout(300)
    check("mobile: fab opens composer", p3.locator(".bnote.composing").count() == 1)
    p3.screenshot(path=str(SHOTS / "10_mobile_brain.png"))
    ctx3.close()

    js_errors = [e for e in errors if "favicon" not in e.lower()]
    check("console: no JS errors", not js_errors, "; ".join(js_errors[:5]))

    # 19. REGRESSION: corrupt localStorage on a COLD start is stashed for recovery, not clobbered.
    # (An in-session reload can't simulate this: the pagehide flush rewrites good state first.)
    ctx2 = browser.new_context(viewport={"width": 1440, "height": 900})
    ctx2.add_init_script("try { localStorage.setItem('slate.state.v1', '{\"v\":1,\"ws\":['); } catch (e) {}")
    p2 = ctx2.new_page()
    p2.goto(BASE)
    p2.wait_for_timeout(700)
    check("regression: corrupt state reseeds UI", p2.locator(".board").count() == 3,
          str(p2.locator(".board").count()))
    stash = p2.evaluate("localStorage.getItem('slate.state.v1.recovery')")
    check("regression: corrupt state stashed under recovery key", stash == '{"v":1,"ws":[', str(stash))
    check("regression: recovery toast shown", p2.locator(".toast", has_text="recovery").count() == 1)
    ctx2.close()

    # 20. REGRESSION: malformed brain payload on a cold load is normalized, never crashes (review finding)
    bad_state = {
        "v": 1, "theme": "light", "view": "brain", "activeWs": "w1",
        "ws": [{"id": "w1", "name": "P", "scroll": {"x": 0, "y": 0}, "boards": []}],
        "brain": {"categories": [
            {"id": "x", "name": "Broken"},                       # missing .notes
            "junk",                                               # not an object
            {"name": 123, "notes": "nope"},                       # bad name + bad notes
            {"id": "y", "name": "OK",
             "notes": [{"id": "n1", "text": "survivor", "created": 1}, "bad", {"nope": 1}]},
        ]},
    }
    ctx4 = browser.new_context(viewport={"width": 1440, "height": 900})
    ctx4.add_init_script(
        "localStorage.setItem('slate.state.v1', " + json.dumps(json.dumps(bad_state)) + ")")
    p4 = ctx4.new_page()
    errs4 = []
    p4.on("pageerror", lambda e: errs4.append(str(e)))
    p4.goto(BASE)
    p4.wait_for_timeout(600)
    check("malformed brain: app boots into brain view",
          p4.evaluate("document.body.dataset.view") == "brain")
    p4.locator("#brainTabs .seg-btn[data-tab='library']").click()
    p4.wait_for_timeout(400)
    check("malformed brain: library renders normalized panes",
          p4.locator(".pane").count() == 3
          and p4.locator(".pane-title", has_text="Untitled").count() == 1,
          str(p4.locator(".pane").count()))
    check("malformed brain: valid note survives", p4.locator(".pnote", has_text="survivor").count() == 1)
    check("malformed brain: no JS errors", not errs4, "; ".join(errs4[:3]))
    ctx4.close()

    browser.close()

fails = [r for r in results if not r[1]]
print(f"\n{len(results) - len(fails)}/{len(results)} passed")
if fails:
    print("FAILURES:")
    for name, _, detail in fails:
        print(" -", name, detail)
    sys.exit(1)
