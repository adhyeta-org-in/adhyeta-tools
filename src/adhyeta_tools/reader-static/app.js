'use strict';

const state = {
    pages: [],
    session: '',  // holds cache-bust token from /pages
    index: 0,
    leftIsImage: true,

    dirty: false,
    saving: false,

    editorMinPx: null,
    editorFontPx: null,

    // Image view state (resets on page navigation)
    zoom: 1,
    panX: 0,
    panY: 0,

    // URL routing
    suppressHash: false,
    lastGoodStem: '',

    // Autosave
    debounceTimer: null,
};

const AUTOSAVE_DEBOUNCE_MS = 5000;
const AUTOSAVE_INTERVAL_MS = 15000;

const panelA = document.getElementById('panel-a');
const panelB = document.getElementById('panel-b');

const btnPrev = document.getElementById('btn-prev');
const btnNext = document.getElementById('btn-next');
const btnSave = document.getElementById('btn-save');
const btnSwap = document.getElementById('btn-swap');

const btnHelp = document.getElementById('btn-help');
const helpOverlay = document.getElementById('help-overlay');
const btnHelpClose = document.getElementById('btn-help-close');

const indicator = document.getElementById('page-indicator');
const dirtyDot = document.getElementById('dirty-dot');
const statusEl = document.getElementById('status');

// ── UI helpers ────────────────────────────────────────────────────────────────
function getTextarea() {
    return document.getElementById('editor');
}

function setStatus(text = '', mode = '') {
    if (!statusEl) return;
    statusEl.textContent = text;
    if (mode) statusEl.setAttribute('data-mode', mode);
    else statusEl.removeAttribute('data-mode');
}

function updateSaveUI() {
    btnSave.disabled = !state.dirty || state.saving;
    dirtyDot.classList.toggle('visible', state.dirty);
}

function setDirty(val) {
    state.dirty = val;
    updateSaveUI();
    if (!val && state.debounceTimer) {
        clearTimeout(state.debounceTimer);
        state.debounceTimer = null;
    }
}

function setSaving(val) {
    state.saving = val;
    updateSaveUI();
}

// ── HTML escape (for innerHTML) ───────────────────────────────────────────────
function escHtml(s) {
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

// ── Help modal ────────────────────────────────────────────────────────────────
function isHelpOpen() {
    return !helpOverlay.classList.contains('hidden');
}
function openHelp() {
    helpOverlay.classList.remove('hidden');
    btnHelpClose.focus();
}
function closeHelp() {
    helpOverlay.classList.add('hidden');
    btnHelp.focus();
}
function toggleHelp() {
    if (isHelpOpen()) closeHelp();
    else openHelp();
}
btnHelp.addEventListener('click', toggleHelp);
btnHelpClose.addEventListener('click', closeHelp);
// Click on backdrop closes (but not clicks inside modal)
helpOverlay.addEventListener('mousedown', (e) => {
    if (e.target === helpOverlay) closeHelp();
});

// ── Image zoom/pan ───────────────────────────────────────────────────────────
const ZOOM_MIN = 1;
const ZOOM_MAX = 6;
const ZOOM_FACTOR = 1.12;
const TEXT_ZOOM_FACTOR = 1.08;

function clamp(v, lo, hi) {
    return Math.max(lo, Math.min(hi, v));
}

function resetView() {
    state.zoom = 1;
    state.panX = 0;
    state.panY = 0;
}

function getImageEl() {
    return document.querySelector('img.page-image');
}

// Transform order is right-to-left; translate first means pan is in screen pixels.
function applyView() {
    const img = getImageEl();
    if (!img) return;
    img.style.transform = `translate(${state.panX}px, ${state.panY}px) scale(${state.zoom})`;
    img.style.cursor = state.zoom > 1 ? 'grab' : 'default';
}

function attachImageInteractions() {
    const img = getImageEl();
    if (!img) return;

    applyView();

    // SHIFT + wheel zoom (zoom-out never below 1)
    img.addEventListener(
        'wheel',
        (e) => {
            if (!e.shiftKey) return;
            e.preventDefault();

            const oldZoom = state.zoom;
            const zoomIn = e.deltaY < 0;
            const newZoom = clamp(
                zoomIn ? oldZoom * ZOOM_FACTOR : oldZoom / ZOOM_FACTOR,
                ZOOM_MIN,
                ZOOM_MAX
            );

            // Zoom-to-cursor: keep point under mouse stable
            const rect = img.getBoundingClientRect();
            const mx = (e.clientX - rect.left) / oldZoom;
            const my = (e.clientY - rect.top) / oldZoom;

            state.zoom = newZoom;
            state.panX += mx * (oldZoom - newZoom);
            state.panY += my * (oldZoom - newZoom);

            if (state.zoom === 1) {
                state.panX = 0;
                state.panY = 0;
            }
            applyView();
        },
        { passive: false }
    );

    // Pan: always when zoom > 1. Once mouse is down, pan starts.
    let dragging = false;
    let startX = 0,
        startY = 0,
        startPanX = 0,
        startPanY = 0;

    img.addEventListener('pointerdown', (e) => {
        if (state.zoom <= 1) return;
        if (e.button !== 0) return; // left mouse only
        dragging = true;
        img.setPointerCapture(e.pointerId);
        startX = e.clientX;
        startY = e.clientY;
        startPanX = state.panX;
        startPanY = state.panY;
        img.style.cursor = 'grabbing';
        e.preventDefault();
    });

    img.addEventListener('pointermove', (e) => {
        if (!dragging) return;
        state.panX = startPanX + (e.clientX - startX);
        state.panY = startPanY + (e.clientY - startY);
        applyView();
    });

    const endDrag = (e) => {
        if (!dragging) return;
        dragging = false;
        try {
            img.releasePointerCapture(e.pointerId);
        } catch { }
        applyView();
    };

    img.addEventListener('pointerup', endDrag);
    img.addEventListener('pointercancel', endDrag);
}

function attachTextZoom() {
    const ta = getTextarea();
    if (!ta) return;

    const curPx = parseFloat(getComputedStyle(ta).fontSize) || 14;

    if (state.editorMinPx == null) {
        state.editorMinPx = curPx;      // minimum comes from CSS on first render
        state.editorFontPx = curPx;
    }

    // Apply current in-memory size to the freshly created textarea
    ta.style.fontSize = `${state.editorFontPx}px`;

    ta.addEventListener(
        'wheel',
        (e) => {
            if (!e.shiftKey) return;

            // Only zoom when mouse is over the text editor (this listener is on textarea)
            e.preventDefault();

            const zoomIn = e.deltaY < 0;
            let next = zoomIn
                ? state.editorFontPx * TEXT_ZOOM_FACTOR
                : state.editorFontPx / TEXT_ZOOM_FACTOR;

            // No upper limit; enforce minimum = CSS-defined size
            next = Math.max(state.editorMinPx, next);

            state.editorFontPx = next;
            ta.style.fontSize = `${state.editorFontPx}px`;
        },
        { passive: false }
    );
}

// ── Routing (URL hash) ────────────────────────────────────────────────────────
function getStemFromHash() {
    const raw = location.hash.replace(/^#/, '').trim();
    if (!raw) return null;
    try {
        return decodeURIComponent(raw);
    } catch {
        return raw;
    }
}

function setHashStem(stem, { replace = false } = {}) {
    const next = `#${encodeURIComponent(stem)}`;
    if (location.hash === next) return;

    state.suppressHash = true;
    if (replace) history.replaceState(null, '', next);
    else location.hash = next;

    setTimeout(() => {
        state.suppressHash = false;
    }, 0);
}

function indexForStem(stem) {
    return state.pages.indexOf(stem);
}

// ── Render panels ─────────────────────────────────────────────────────────────
function renderPanels(stem, textContent) {
    const v = state.session ? `?v=${encodeURIComponent(state.session)}` : '';
    const imgHTML = `<img class="page-image" src="/image/${stem}${v}" alt="Page ${stem}" draggable="false" />`;
    const txtHTML = `<textarea id="editor" spellcheck="false">${escHtml(
        textContent ?? ''
    )}</textarea>`;

    if (state.leftIsImage) {
        panelA.innerHTML = imgHTML;
        panelB.innerHTML = txtHTML;
    } else {
        panelA.innerHTML = txtHTML;
        panelB.innerHTML = imgHTML;
    }

    const ta = getTextarea();
    if (ta) {
        ta.addEventListener(
            'input',
            () => {
                if (!state.dirty) setDirty(true);
                setStatus('Unsaved', 'dirty');
                scheduleDebouncedSave();
            },
            { once: false }
        );
    }

    // Image element is recreated on each render -> reattach interactions each time.
    attachTextZoom();
    attachImageInteractions();
}

function updateNav() {
    const total = state.pages.length;
    const idx = state.index;
    const stem = total ? state.pages[idx] : '';
    indicator.textContent = total ? `${idx + 1}/${total} • ${stem}` : '0/0';
    document.title = total ? `Proofreader — ${stem} (${idx + 1}/${total})` : 'Proofreader';

    btnPrev.disabled = idx === 0;
    btnNext.disabled = idx === total - 1;

    updateSaveUI();
}

// ── Load page ─────────────────────────────────────────────────────────────────
async function loadPage(index, { updateHash = true, pushHash = false } = {}) {
    const stem = state.pages[index];
    if (!stem) return false;

    try {
        setStatus('Loading…', 'saving');
        const resp = await fetch(`/text/${stem}`, { cache: 'no-store' });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        const content = data?.content ?? '';

        state.index = index;
        state.lastGoodStem = stem;

        resetView(); // resets zoom/pan on navigation
        renderPanels(stem, content);
        setDirty(false);

        updateNav();
        setStatus('Saved', 'ok');

        if (updateHash) setHashStem(stem, { replace: !pushHash });
        return true;
    } catch (err) {
        setStatus('Load failed', 'error');
        return false;
    }
}

// ── Save (returns true/false) ─────────────────────────────────────────────────
async function save({ reason = 'manual', keepalive = false } = {}) {
    if (!state.dirty) return true;
    if (state.saving) return false;

    const stem = state.pages[state.index];
    const content = getTextarea()?.value ?? '';

    try {
        setSaving(true);
        setStatus(reason === 'manual' ? 'Saving…' : 'Autosaving…', 'saving');

        const resp = await fetch(`/text/${stem}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content }),
            keepalive,
        });

        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json().catch(() => ({}));
        if (data?.ok !== true) throw new Error('Server did not confirm ok');

        setDirty(false);
        setStatus(reason === 'manual' ? 'Saved' : 'Autosaved', 'ok');
        return true;
    } catch (err) {
        setStatus('Save failed (not moving)', 'error');
        // Keep dirty=true
        return false;
    } finally {
        setSaving(false);
    }
}

// ── Autosave ─────────────────────────────────────────────────────────────────
function scheduleDebouncedSave() {
    if (state.debounceTimer) clearTimeout(state.debounceTimer);
    state.debounceTimer = setTimeout(() => {
        if (state.dirty) save({ reason: 'debounce' });
    }, AUTOSAVE_DEBOUNCE_MS);
}

// 15s safety net: if still dirty, try an autosave.
setInterval(() => {
    if (state.dirty && !state.saving) save({ reason: 'interval' });
}, AUTOSAVE_INTERVAL_MS);

// Try to save when the tab is being discarded (best-effort).
window.addEventListener('pagehide', () => {
    if (state.dirty && !state.saving) save({ reason: 'pagehide', keepalive: true });
});

// ── Prevent refresh/close when dirty ──────────────────────────────────────────
window.addEventListener('beforeunload', (e) => {
    if (!state.dirty) return;
    e.preventDefault();
    e.returnValue = '';
});

// ── Navigate ──────────────────────────────────────────────────────────────────
async function navigate(delta) {
    const next = state.index + delta;
    if (next < 0 || next >= state.pages.length) return;

    const ok = await save({ reason: 'navigate' });
    if (!ok) return;

    await loadPage(next, { updateHash: true, pushHash: true });
}

// ── Manual URL editing support ────────────────────────────────────────────────
window.addEventListener('hashchange', async () => {
    if (state.suppressHash) return;
    if (!state.pages.length) return;

    const stem = getStemFromHash();
    if (!stem) {
        setHashStem(state.pages[state.index], { replace: true });
        return;
    }

    const idx = indexForStem(stem);
    if (idx < 0) {
        setStatus(`Unknown page: ${stem}`, 'error');
        setHashStem(state.pages[state.index], { replace: true });
        return;
    }

    if (idx === state.index) return;

    const ok = await save({ reason: 'hashchange' });
    if (!ok) {
        setHashStem(state.pages[state.index], { replace: true });
        return;
    }

    await loadPage(idx, { updateHash: false });
});

// ── Panel swap ────────────────────────────────────────────────────────────────
btnSwap.addEventListener('click', () => {
    const ta = getTextarea();
    // Capture live content before re-render wipes the textarea
    const liveContent = ta ? ta.value : '';
    state.leftIsImage = !state.leftIsImage;
    const stem = state.pages[state.index];
    renderPanels(stem, liveContent);

    updateSaveUI();
});

// ── Resizer ───────────────────────────────────────────────────────────────────
(function () {
    const resizer = document.getElementById('resizer');
    let active = false,
        startX = 0,
        aW = 0,
        bW = 0;

    resizer.addEventListener('mousedown', (e) => {
        active = true;
        startX = e.clientX;
        aW = panelA.offsetWidth;
        bW = panelB.offsetWidth;
        resizer.classList.add('dragging');
        e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
        if (!active) return;
        const dx = e.clientX - startX;
        const newA = Math.max(180, aW + dx);
        const newB = Math.max(180, aW + bW - newA);
        panelA.style.flex = 'none';
        panelB.style.flex = 'none';
        panelA.style.width = newA + 'px';
        panelB.style.width = newB + 'px';
    });

    document.addEventListener('mouseup', () => {
        if (!active) return;
        active = false;
        resizer.classList.remove('dragging');
    });
})();

// ── Keyboard ──────────────────────────────────────────────────────────────────
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && isHelpOpen()) {
        e.preventDefault();
        closeHelp();
        return;
    }

    // Toggle help on '?'
    if (!e.ctrlKey && !e.metaKey && !e.altKey && !e.shiftKey && e.key === '?') {
        e.preventDefault();
        toggleHelp();
        return;
    }
    if (!e.ctrlKey && !e.metaKey && !e.altKey && e.shiftKey && e.key === '/') {
        // Many layouts produce '?' as Shift + '/'
        e.preventDefault();
        toggleHelp();
        return;
    }

    if (e.altKey && e.key === 'ArrowLeft') {
        e.preventDefault();
        navigate(-1);
    } else if (e.altKey && e.key === 'ArrowRight') {
        e.preventDefault();
        navigate(+1);
    } else if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        save({ reason: 'manual' });
    }
});

// ── Button wiring ─────────────────────────────────────────────────────────────
btnPrev.addEventListener('click', () => navigate(-1));
btnNext.addEventListener('click', () => navigate(+1));
btnSave.addEventListener('click', () => save({ reason: 'manual' }));

// ── Init ──────────────────────────────────────────────────────────────────────
(async () => {
    try {
        const { pages, session } = await fetch('/pages', { cache: 'no-store' }).then((r) => r.json());
        state.pages = pages || [];
        state.session = session || '';

        if (!state.pages.length) {
            panelA.innerHTML =
                '<p style="color:#666;padding:20px;">No pages found in image directory.</p>';
            indicator.textContent = '0/0';
            document.title = 'Proofreader';
            setStatus('', '');
            return;
        }

        const stem = getStemFromHash();
        const idx = stem ? indexForStem(stem) : -1;

        if (idx >= 0) {
            await loadPage(idx, { updateHash: false });
        } else {
            await loadPage(0, { updateHash: true, pushHash: false });
        }
    } catch (err) {
        setStatus('Init failed', 'error');
    }
})();
