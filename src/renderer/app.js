/* SlideTistic renderer. Plain JS, no bundler (SlideFluid pattern). All outside access goes through
   window.slidetistic (preload.js). */
'use strict';

const api = window.slidetistic;
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const isMac = navigator.platform.toLowerCase().includes('mac');

const S = { decks: [], sel: null, tab: 'review', filter: 'all', checks: [], settings: {}, info: {}, viewer: null };
let nextId = 1;

const SHOUT = {
  canva: ['CANVA DETECTED!', 'Buckle up, we got a gRaPhIc dEsIgNeR on our hands.'],
  google: ['GOOGLE SLIDES DETECTED!', 'Someone “collaborated” on this. Expect stand-in fonts and links to YouTube.'],
  keynote: ['KEYNOTE DETECTED!', 'Bold of them to assume the show machine has Avenir.'],
  pdf: ['PDF IN A TRENCH COAT DETECTED!', 'Every slide is a picture. Nothing here can be edited, only looked at.'],
};
const TAGLINES = { pro: ['PowerPoint is my special interest.'],
  fun: ['graphic design is my passion', 'Now with 40% more Comic Sans', 'Choo choo, Calibri (MS)',
        'Your fonts have left the station', 'Kerning? I hardly know her', 'All aboard the struggle bus'] };
const WORDS = {
  pro: { fixed: 'fixed', look: 'to look at', broken: 'still broken', scanning: 'Checking…', repairing: 'Repairing…' },
  fun: { fixed: "choo-choo'd", look: 'sus', broken: 'derailed', scanning: 'Sniffing the slides…', repairing: 'Stoking the boiler…' },
};
const words = () => WORDS[S.settings.skin === 'fun' ? 'fun' : 'pro'];
const KIND_LABEL = { font: 'Font fix', placement: 'Placement', layout: 'Layout fit', media: 'Media & playback', content: 'Content' };

// ---------------------------------------------------------------------------------------------
// Startup

async function init() {
  S.settings = await api.getSettings();
  S.info = await api.info();
  S.checks = await api.listChecks();
  applySkin();
  $('year').textContent = new Date().getFullYear();
  wireStatic();
  api.onEngineEvent(onEngineEvent);
  api.onWatchFound((files) => addFiles(files, true));
  api.onUpdateStatus(onUpdateStatus);
  S.tab = S.settings.lastTab || 'review';
  render();
}

function applySkin() {
  const skin = S.settings.skin === 'fun' ? 'fun' : 'pro';
  document.body.dataset.skin = skin;
  const pool = TAGLINES[skin];
  $('tagline').textContent = pool[Math.floor(Math.random() * pool.length)];
}

// ---------------------------------------------------------------------------------------------
// Queue

async function addPaths(paths) {
  if (!paths.length) return;
  addFiles(await api.expand(paths), false);
}

function addFiles(files, fromWatch) {
  let added = 0;
  for (const f of files) {
    const existing = S.decks.find((d) => d.path === f.path);
    if (existing) {
      if (fromWatch && existing.status !== 'scanning' && existing.status !== 'repairing') scan(existing);
      continue;
    }
    const deck = { id: `d${nextId++}`, path: f.path, name: f.name.replace(/\.(pptx|pptm|ppt|key)$/i, ''), size: f.size,
                   ext: f.ext, status: 'queued', stage: '', review: null, version: 0 };
    S.decks.push(deck);
    added++;
    if (f.isDir) { fail(deck, 'This is a folder of slide images, not a PowerPoint file.'); continue; }
    if (f.ext === '.key') { fail(deck, 'Keynote file: export it to PowerPoint (File ▸ Export To ▸ PowerPoint) and drop the .pptx. Automatic conversion is coming.'); continue; }
    if (f.ext === '.ppt') { fail(deck, 'Old .ppt format: open it in PowerPoint and Save As .pptx, then drop that.'); continue; }
    if (f.size > 1024 * 1024 * 1024) toast(`${f.name} is ${(f.size / 1073741824).toFixed(1)} GB: checking it may take a while.`);
    scan(deck);
  }
  if (added && !S.sel) S.sel = S.decks[S.decks.length - added].id;
  if (fromWatch && added) toast(`Watch folder: ${added} new deck${added > 1 ? 's' : ''} added.`);
  render();
}

function fail(deck, message) { deck.status = 'error'; deck.error = message; }

function optionsFor(deck) {
  const preset = presetFor(deck);
  const saved = (S.settings.presets || {})[preset] || {};
  const checks = [], fixes = [];
  for (const c of S.checks) {
    const o = saved[c.id] || {};
    if (o.check ?? c.default_check) checks.push(c.id);
    if (!c.report_only && (o.fix ?? c.default_fix) && (o.check ?? c.default_check)) fixes.push(c.id);
  }
  return { checks, fixes, preset };
}

function presetFor(deck) {
  const kind = deck.review?.data?.source?.kind;
  return deck.presetOverride || (['canva', 'google', 'keynote'].includes(kind) ? kind : 'any');
}

async function scan(deck) {
  deck.status = 'scanning'; deck.stage = words().scanning; deck.error = null; deck.kind = 'scan';
  render();
  await api.scan(deck.id, deck.path, optionsFor(deck));
}

async function repair(deck) {
  if (!deck || deck.status === 'error' || deck.status === 'scanning' || deck.status === 'repairing') return;
  deck.status = 'repairing'; deck.stage = words().repairing; deck.kind = 'repair'; deck.progress = null;
  render();
  const r = await api.repair(deck.id, deck.path, optionsFor(deck));
  deck.output = r.output;
}

function repairAll() {
  const todo = S.decks.filter((d) => d.status === 'scanned');
  if (!todo.length) { toast('Nothing to repair: add decks, or wait for them to finish checking.'); return; }
  todo.forEach(repair);
  toast(`Repairing ${todo.length} deck${todo.length > 1 ? 's' : ''}, one after another.`);
}

function removeDeck(deck) {
  if (deck.status === 'scanning' || deck.status === 'repairing') api.cancel(deck.id);
  const i = S.decks.indexOf(deck);
  S.decks.splice(i, 1);
  if (S.sel === deck.id) S.sel = (S.decks[i] || S.decks[i - 1] || {}).id || null;
  render();
}

const selected = () => S.decks.find((d) => d.id === S.sel);

// ---------------------------------------------------------------------------------------------
// Engine events

const STAGES = { scan: 'Checking', fix: 'Fixing', fit: 'Fitting text', render: 'Drawing the slides in PowerPoint',
                 safety: 'Final safety check', rescan: 'Re-checking the repaired deck' };

async function onEngineEvent(ev) {
  const deck = S.decks.find((d) => d.id === ev.deckId);
  if (!deck) return;
  if (ev.type === 'progress') {
    const base = STAGES[ev.stage] || ev.stage;
    if (ev.stage === 'fit') deck.stage = `${base}: round ${ev.round} of ${ev.rounds}`;
    else if (ev.index) deck.stage = `${base}: ${ev.check} (${ev.index} of ${ev.total})`;
    else deck.stage = base;
    deck.progress = ev.index && ev.total ? ev.index / ev.total : null;
    renderBusyOnly(deck);
    return;
  }
  if (ev.type === 'error') { deck.error = ev.message; return; }
  if (ev.type === 'warn') { toast(ev.message); return; }
  if (ev.type === 'undone') {
    deck.version++;
    await loadReview(deck);
    toast(`Slide ${ev.slide} is back to how it was before the layout fixes.`);
    render();
    if (S.viewer) renderViewer();
    return;
  }
  if (ev.type === 'done') {
    if (ev.cancelled) { deck.status = deck.review ? (deck.output ? 'repaired' : 'scanned') : 'queued'; render(); return; }
    if (ev.kind === 'undo') { deck.busyUndo = false; render(); return; }
    if (ev.code) {
      fail(deck, deck.error || 'Something went wrong. Settings ▸ Diagnostics has the details.');
    } else {
      deck.status = ev.kind === 'repair' ? 'repaired' : 'scanned';
      deck.version++;
      await loadReview(deck);
      if (ev.kind === 'repair' && deck.review?.data?.output) deck.output = deck.review.data.output;
    }
    render();
  }
}

async function loadReview(deck) {
  deck.review = await api.loadReview(deck.id);
}

// ---------------------------------------------------------------------------------------------
// Rendering

function render() {
  renderQueue();
  const deck = selected();
  $('empty').hidden = !!deck;
  $('results').hidden = !deck;
  $('btn-repair-all').disabled = !S.decks.some((d) => d.status === 'scanned');
  if (deck) renderResults(deck);
}

function summaryChips(sum) {
  const w = words();
  return `<span class="chip g">✓ ${sum.green_fixed} ${w.fixed}</span><span class="chip y">! ${sum.yellow} ${w.look}</span>` +
         `<span class="chip r">✕ ${sum.red + sum.tool_error} ${w.broken}</span>`;
}

function renderQueue() {
  $('queue-count').textContent = S.decks.length ? `${S.decks.length} deck${S.decks.length > 1 ? 's' : ''}` : '';
  $('queue').innerHTML = S.decks.map((d) => {
    const sum = d.review?.data?.summary;
    let body;
    if (d.status === 'error') body = `<div class="chips"><span class="chip r">✕ ${esc(d.error)}</span></div>`;
    else if (d.status === 'scanning' || d.status === 'repairing' || d.status === 'queued')
      body = `<div class="chips"><span class="chip v">${esc(d.status === 'queued' ? 'Waiting…' : d.stage)}</span></div><div class="mini-bar"><i></i></div>`;
    else if (sum) body = `<div class="chips">${summaryChips(sum).replace(/ (fixed|to look at|still broken|choo-choo'd|sus|derailed)/g, '')}</div>`;
    else body = '';
    const sub = [d.review?.data?.source?.kind, d.status === 'repaired' ? 'repaired' : null].filter(Boolean).join(' · ');
    return `<div class="card ${d.id === S.sel ? 'sel' : ''} ${d.status === 'error' ? 'err' : ''}" data-id="${d.id}" title="${esc(d.path)}">
      <button class="icon x" data-remove="${d.id}" aria-label="Remove from queue" title="Remove from queue (the file isn't touched)">✕</button>
      <div class="nm">${esc(d.name)}</div>${sub ? `<div class="sub">${esc(sub)}</div>` : ''}${body}</div>`;
  }).join('');
}

function renderBusyOnly(deck) {
  if (deck.id === S.sel) {
    $('busy-title').textContent = deck.status === 'repairing' ? words().repairing : words().scanning;
    $('busy-detail').textContent = deck.stage || '';
    const bar = $('busy-bar');
    if (deck.progress != null) { bar.classList.add('known'); bar.style.width = `${Math.round(deck.progress * 100)}%`; }
    else { bar.classList.remove('known'); bar.style.width = ''; }
  }
  renderQueue();
}

function renderResults(deck) {
  const data = deck.review?.data;
  $('deck-name').textContent = deck.name;
  $('deck-chips').innerHTML = data ? summaryChips(data.summary) : '';
  const busy = deck.status === 'scanning' || deck.status === 'repairing' || deck.status === 'queued';
  $('busy').hidden = !busy;
  if (busy) renderBusyOnly(deck);
  $('btn-repair').disabled = busy || deck.status === 'error';
  $('btn-repair').textContent = deck.status === 'repaired' ? 'Repair again' : 'Repair';
  $('btn-export').disabled = deck.status !== 'repaired' || S.settings.quickRepair;
  $('btn-finder').textContent = isMac ? 'Show in Finder' : 'Show in Explorer';

  const src = data?.source;
  $('source').hidden = !(src && SHOUT[src.kind]);
  if (src && SHOUT[src.kind]) $('source').innerHTML = `<b>${esc(SHOUT[src.kind][0])}</b> ${esc(SHOUT[src.kind][1])}<small>${esc(src.message)}</small>`;

  const off = [...new Set((data?.findings || []).filter((f) => f.status === 'red' && f.subject === 'off-slide' && f.slide).map((f) => f.slide))].sort((a, b) => a - b);
  $('alert').hidden = !off.length;
  if (off.length) $('alert').innerHTML = `✕ Text runs off the slide on slide${off.length > 1 ? 's' : ''} ${off.map((n) => `<a data-slide="${n}">${n}</a>`).join(', ')}. Fix before the show.`;

  $('saved').hidden = !(deck.status === 'repaired' && deck.output);
  if (deck.output) {
    const name = deck.output.split(/[\\/]/).pop();
    $('saved').innerHTML = `Saved <b title="${esc(deck.output)}">${esc(name)}</b> · <a data-open-output>${isMac ? 'Show in Finder' : 'Show in Explorer'}</a> · <a data-open-mended>Open</a>`;
  }

  if (deck.status === 'error') {
    $('tab-review').innerHTML = `<div class="alert">✕ ${esc(deck.error)}</div>`;
    ['findings', 'media', 'options'].forEach((t) => { $(`tab-${t}`).innerHTML = ''; });
  } else {
    renderReview(deck);
    renderFindings(deck);
    renderMedia(deck);
    renderOptions(deck);
  }
  document.querySelectorAll('#tabs button').forEach((b) => b.classList.toggle('on', b.dataset.tab === S.tab));
  ['review', 'findings', 'media', 'options'].forEach((t) => { $(`tab-${t}`).hidden = t !== S.tab; });
}

function imgUrl(deck, name) {
  if (!name) return null;
  const base = deck.review.dir.startsWith('http') ? deck.review.dir : `file://${deck.review.dir}`;
  return `${base}/${encodeURIComponent(name)}?v=${deck.version}`;
}

function boxesHtml(boxes) {
  const why = S.settings.showWhy;
  return (boxes || []).map((b) => {
    const tip = b.label + (why && b.detail ? `\nWhy: ${b.detail}` : '');
    const flip = b.left + b.width / 2 > 50 ? ' flip' : '';
    return `<div class="box ${b.kind} ${b.mode}${flip}" style="left:${b.left.toFixed(2)}%;top:${b.top.toFixed(2)}%;width:${b.width.toFixed(2)}%;height:${b.height.toFixed(2)}%">` +
           `<span class="tag">${esc(KIND_LABEL[b.kind] || b.kind)}</span><span class="tip">${esc(tip)}</span></div>`;
  }).join('');
}

function frameHtml(deck, caption, name, boxes, slide) {
  const url = imgUrl(deck, name);
  const inner = url ? `<img src="${url}" alt="${esc(caption)} slide ${slide}" draggable="false">` : '<div class="none">Not drawn (hidden slide)</div>';
  return `<div><span class="cap">${esc(caption)}</span><div class="frame" data-fs="${slide}">${inner}${boxesHtml(boxes)}</div></div>`;
}

function renderReview(deck) {
  const data = deck.review?.data;
  const el = $('tab-review');
  if (!data) { el.innerHTML = '<p class="note">The review appears once the deck has been checked.</p>'; return; }
  const visuals = data.visuals || [];
  if (!visuals.length) {
    el.innerHTML = `<p class="note">${esc(data.visual_note || (deck.status === 'repaired' ? 'No slide changed visually.' : 'Nothing to show on the slides. See Findings.'))}</p>`;
    return;
  }
  const repaired = !!data.output;
  const legend = `<div class="legend">${Object.entries(KIND_LABEL).map(([k, l]) => `<span><i class="sw" style="border-color:var(--k-${k})"></i>${l}</span>`).join('')}` +
                 '<span>━ changed · ┅ needs a look · ✕ broken</span><span>Hover a box for details · double-click a slide for full screen</span></div>';
  const tiers = { 1: 'Broken: fix before the show', 2: 'Changes SlideTistic made: check them', 3: 'Needs a look' };
  let html = legend;
  for (const t of [1, 2, 3]) {
    const block = visuals.filter((v) => v.tier === t);
    if (!block.length) continue;
    html += `<h3 class="tier t${t}">${t}. ${tiers[t]} <small>· ${block.length} slide${block.length > 1 ? 's' : ''}</small></h3>`;
    for (const v of block) html += slideCard(deck, v, repaired);
  }
  const same = visuals.filter((v) => v.tier === 4).map((v) => v.slide);
  if (same.length) html += `<p class="fold">4. Changed underneath, looks identical: slide${same.length > 1 ? 's' : ''} ${ranges(same)}.</p>`;
  el.innerHTML = html;
}

function slideCard(deck, v, repaired) {
  const canUndo = repaired && deck.review.data.prefit && !v.undone && (v.after_boxes || []).some((b) => b.mode === 'changed');
  const pair = repaired
    ? `<div class="pair">${frameHtml(deck, 'Before', v.before_png, v.before_boxes, v.slide)}${frameHtml(deck, v.undone ? 'After (layout changes undone)' : 'After', v.after_png, v.after_boxes, v.slide)}</div>`
    : `<div class="single">${frameHtml(deck, 'As PowerPoint draws it', v.before_png, v.before_boxes, v.slide)}</div>`;
  return `<section class="slide ${v.undone ? 'undone' : ''}" id="slide-${v.slide}"><div class="slide-head"><b>Slide ${v.slide}</b>
    <button class="btn" data-fs="${v.slide}" title="Full screen (F)">⤢ Full screen</button>
    ${canUndo ? `<button class="btn" data-undo="${v.slide}" title="Put this slide back the way it was before layout fixes; font fixes stay">↶ Undo slide</button>` : ''}
    <button class="btn" data-ppt="${v.slide}" title="Open in PowerPoint at this slide">PowerPoint ↗</button></div>${pair}</section>`;
}

function ranges(nums) {
  const out = []; let start = null;
  nums.forEach((n, i) => {
    if (start === null) start = n;
    if (i + 1 === nums.length || nums[i + 1] !== n + 1) { out.push(start === n ? `${n}` : `${start}–${n}`); start = null; }
  });
  return out.join(', ');
}

const ORDER = { red: 0, tool_error: 1, yellow: 2, green_fixed: 3 };
const ICON = { red: ['✕', 'r', 'Broken'], tool_error: ['?', 'r', "Couldn't run"], yellow: ['!', 'y', 'Look at'], green_fixed: ['✓', 'g', 'Fixed'] };

function renderFindings(deck) {
  const data = deck.review?.data;
  const el = $('tab-findings');
  if (!data) { el.innerHTML = ''; return; }
  const titles = Object.fromEntries((data.checks || []).map((c) => [c.id, c.title]));
  const rows = (data.findings || []).filter((f) => !f.informational && (S.filter === 'all' || f.status === S.filter))
    .sort((a, b) => (ORDER[a.status] ?? 9) - (ORDER[b.status] ?? 9) || (a.slide || 0) - (b.slide || 0));
  const hasSlide = new Set((data.visuals || []).map((v) => v.slide));
  const filters = [['all', 'All'], ['red', '✕ Broken'], ['yellow', '! Look at'], ['green_fixed', '✓ Fixed']]
    .map(([k, l]) => `<button data-filter="${k}" class="${S.filter === k ? 'on' : ''}">${l}</button>`).join('');
  const body = rows.map((f) => {
    const [icon, cls, word] = ICON[f.status] || ['·', '', f.status];
    const where = f.slide ? `Slide ${f.slide}${f.shape_name ? ` · ${esc(f.shape_name)}` : ''}` : 'Whole deck';
    const why = S.settings.showWhy ? (f.evidence?.rule || '') : '';
    const extra = [f.evidence?.fix_result, f.evidence?.introduced_by ? `Introduced by ${f.evidence.introduced_by}` : '', why ? `Why: ${why}` : '']
      .filter(Boolean).map((x) => `<div class="why">${esc(x)}</div>`).join('');
    const jump = f.slide && hasSlide.has(f.slide) ? ` class="jump" data-jump="${f.slide}"` : '';
    return `<tr${jump}><td class="s ${cls}">${icon} ${word}</td><td>${where}</td><td>${esc(f.check_id)} ${esc(titles[f.check_id] || '')}</td><td>${esc(f.message)}${extra}</td></tr>`;
  }).join('') || '<tr><td colspan="4" class="note">Nothing here.</td></tr>';
  el.innerHTML = `<div class="filters">${filters}</div><div class="wrap"><table><thead><tr><th></th><th>Where</th><th>Check</th><th>What</th></tr></thead><tbody>${body}</tbody></table></div>`;
}

function renderMedia(deck) {
  const data = deck.review?.data;
  const el = $('tab-media');
  if (!data) { el.innerHTML = ''; return; }
  const inv = data.inventory || [];
  const dls = data.downloads || [];
  const cols = [['Slide', 'slide'], ['Slide name', 'slide_name'], ['Media', 'media'], ['Duration', 'duration'], ['Starts', 'starts'],
                ['Loop', 'loop'], ['Volume', 'volume'], ['Embedded/linked', 'storage'], ['Format', 'format'], ['Resolution', 'resolution'], ['MB', 'mb'], ['Risk', 'risk']];
  let html = '<div class="row" style="justify-content:flex-end"><button class="btn" data-media="csv">Export CSV</button><button class="btn" data-media="xlsx">Export Excel</button></div>';
  html += '<h3 class="section-title">Video and audio</h3>';
  html += inv.length ? `<div class="wrap"><table><thead><tr>${cols.map(([c]) => `<th>${c}</th>`).join('')}</tr></thead><tbody>${
    inv.map((r) => `<tr>${cols.map(([, k]) => `<td>${esc(r[k])}</td>`).join('')}</tr>`).join('')}</tbody></table></div><p class="note">${esc(data.totals)}</p>`
    : '<p class="note">No video or audio in this deck.</p>';
  html += '<h3 class="section-title">To download <span class="note">fetch these and embed them before the show</span></h3>';
  html += dls.length ? `<div class="wrap"><table><thead><tr><th>Slide</th><th>Slide name</th><th>Site</th><th>Found in</th><th>Link</th></tr></thead><tbody>${
    dls.map((r) => `<tr><td>${r.slide}</td><td>${esc(r.slide_name)}</td><td>${esc(r.site)}</td><td>${esc(r.found_in)}</td><td><a data-url="${esc(r.url)}" style="color:var(--accent);cursor:pointer">${esc(r.url)}</a></td></tr>`).join('')}</tbody></table></div>`
    : '<p class="note">No video or media links found.</p>';
  el.innerHTML = html;
}

function renderOptions(deck) {
  const el = $('tab-options');
  const preset = presetFor(deck);
  const saved = (S.settings.presets || {})[preset] || {};
  const groups = {};
  for (const c of S.checks) (groups[c.group] = groups[c.group] || []).push(c);
  const presetSel = `<div class="preset">Settings for <select id="preset-select">${['canva', 'google', 'keynote', 'any'].map((p) =>
    `<option value="${p}" ${p === preset ? 'selected' : ''}>${p === 'any' ? 'PowerPoint / other' : p[0].toUpperCase() + p.slice(1)} decks</option>`).join('')}</select>
    <span class="note">Changes are remembered for every ${preset === 'any' ? 'other' : preset} deck.</span><span class="grow"></span>
    <button class="btn" id="btn-rescan">Re-check with these settings</button></div>`;
  const html = Object.entries(groups).map(([g, list]) => `<div class="opt-group"><h3>${esc(g)}</h3>${list.map((c) => {
    const o = saved[c.id] || {};
    const chk = o.check ?? c.default_check;
    const fix = c.report_only ? false : (o.fix ?? c.default_fix);
    return `<div class="opt"><span class="id">${c.id}</span><span>${esc(c.title)}<small>${esc(c.description)}</small></span>
      <label class="toggle"><input type="checkbox" data-opt="${c.id}" data-k="check" ${chk ? 'checked' : ''}> Check</label>
      <label class="toggle" title="${c.report_only ? 'Report only: no automatic fix' : ''}"><input type="checkbox" data-opt="${c.id}" data-k="fix" ${fix ? 'checked' : ''} ${c.report_only || !chk ? 'disabled' : ''}> Fix</label></div>`;
  }).join('')}</div>`).join('');
  el.innerHTML = presetSel + html;
}

// ---------------------------------------------------------------------------------------------
// Full-screen viewer

function openViewer(slide) {
  const deck = selected();
  const visuals = deck?.review?.data?.visuals || [];
  const idx = visuals.findIndex((v) => v.slide === slide);
  if (idx < 0) return;
  S.viewer = { idx, mode: S.viewer?.mode || 'side', flipShow: 'after' };
  $('viewer').hidden = false;
  renderViewer();
}

function renderViewer() {
  const deck = selected();
  const visuals = deck?.review?.data?.visuals || [];
  const v = visuals[S.viewer.idx];
  if (!v) { closeViewer(); return; }
  const repaired = !!deck.review.data.output;
  $('viewer-title').textContent = `Slide ${v.slide}  ·  ${S.viewer.idx + 1} of ${visuals.length}`;
  const canUndo = repaired && deck.review.data.prefit && !v.undone && (v.after_boxes || []).some((b) => b.mode === 'changed');
  $('v-undo').hidden = !canUndo;
  $('v-mode').hidden = !repaired;
  let html;
  if (!repaired) {
    html = `<div class="pane">${frameHtml(deck, 'As PowerPoint draws it', v.before_png, v.before_boxes, v.slide)}</div>`;
    $('viewer-mode').textContent = '';
  } else if (S.viewer.mode === 'side') {
    html = `<div class="pane">${frameHtml(deck, 'Before', v.before_png, v.before_boxes, v.slide)}</div>` +
           `<div class="pane">${frameHtml(deck, v.undone ? 'After (undone)' : 'After', v.after_png, v.after_boxes, v.slide)}</div>`;
    $('viewer-mode').textContent = 'side by side';
  } else {
    const before = S.viewer.flipShow === 'before';
    html = `<div class="pane" style="max-width:1400px">${frameHtml(deck, before ? 'BEFORE' : 'AFTER', before ? v.before_png : v.after_png,
            before ? v.before_boxes : v.after_boxes, v.slide)}</div>`;
    $('viewer-mode').textContent = `flip view · showing ${before ? 'BEFORE' : 'AFTER'} (hold Space or press B)`;
  }
  $('viewer-stage').innerHTML = html;
}

function closeViewer() { S.viewer = null; $('viewer').hidden = true; }
function viewerStep(d) {
  const n = (selected()?.review?.data?.visuals || []).length;
  if (!n) return;
  S.viewer.idx = (S.viewer.idx + d + n) % n;
  renderViewer();
}
const viewerSlide = () => (selected()?.review?.data?.visuals || [])[S.viewer?.idx]?.slide;

// ---------------------------------------------------------------------------------------------
// Actions

async function undoSlide(slide) {
  const deck = selected();
  if (!deck?.output) return;
  toast(`Undoing slide ${slide}…`);
  await api.undoSlide(deck.id, deck.output, slide);
}

async function openInPowerPoint(slide) {
  const deck = selected();
  if (!deck) return;
  const file = deck.status === 'repaired' && deck.output ? deck.output : deck.path;
  toast(`Opening slide ${slide} in PowerPoint…`);
  const r = await api.openAtSlide(file, slide);
  if (r?.note) toast(r.note);
  if (r && !r.ok && r.error) toast(`PowerPoint didn't open: ${r.error}`);
}

function jumpToSlide(slide) {
  S.tab = 'review';
  render();
  requestAnimationFrame(() => $(`slide-${slide}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
}

function setTab(t) { S.tab = t; api.setSetting('lastTab', t); render(); }

let toastTimer = null;
function toast(msg) {
  const t = $('toast');
  t.textContent = msg; t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, 3600);
}

// ---------------------------------------------------------------------------------------------
// Settings

async function openSettings() {
  const s = S.settings;
  $('s-output').value = s.outputFolder || ''; $('s-suffix').value = s.suffix; $('s-safe').value = s.safeZonePct;
  $('s-quick').checked = !!s.quickRepair; $('s-watch').value = s.watchFolder || ''; $('s-crew').value = s.crewFonts || '';
  $('s-why').checked = !!s.showWhy;
  document.querySelectorAll('.skin').forEach((b) => b.classList.toggle('on', b.dataset.skin === s.skin));
  $('diag').innerHTML = `SlideTistic ${esc(S.info.version)} · ${esc(S.info.platform)} · PowerPoint ${S.info.powerpoint === null ? 'n/a' : S.info.powerpoint ? 'found' : 'not found (no visual review or layout fixes)'}<br>` +
    `${S.checks.length} checks: ${S.checks.map((c) => `${c.id} v${c.version}`).join(', ')}<br>Log: ${esc(S.info.logFile)}`;
  $('d-log').textContent = await api.logTail(120);
  $('settings').hidden = false;
}

async function setSetting(key, value) {
  S.settings = await api.setSetting(key, value);
  if (key === 'skin') applySkin();
  render();
}

// ---------------------------------------------------------------------------------------------
// Updates (global CLAUDE recipe: show the raw error)

const fmtSpeed = (bps) => (bps > 1048576 ? `${(bps / 1048576).toFixed(1)} MB/s` : `${Math.round(bps / 1024)} KB/s`);
const fmtETA = (s) => (s < 60 ? `~${Math.round(s)}s left` : `~${Math.floor(s / 60)}m ${Math.round(s % 60)}s left`);

function onUpdateStatus(st) {
  const line = $('d-update-status');
  const bar = $('d-update-bar');
  const fill = (pct) => { bar.hidden = false; bar.firstElementChild.style.width = `${pct}%`; };
  if (st.type === 'checking') { line.textContent = 'Checking GitHub Releases…'; bar.hidden = true; }
  else if (st.type === 'not-available') { line.textContent = 'You have the latest version.'; bar.hidden = true; }
  else if (st.type === 'available') { line.textContent = `Update available: v${st.version}, downloading…`; fill(0); api.downloadUpdate(); }
  else if (st.type === 'progress') {
    const parts = [`${Math.round(st.percent)}%`, `${(st.transferred / 1048576).toFixed(1)} / ${(st.total / 1048576).toFixed(1)} MB`];
    if (st.bytesPerSecond > 0) parts.push(fmtSpeed(st.bytesPerSecond), fmtETA((st.total - st.transferred) / st.bytesPerSecond));
    line.textContent = parts.join('  ·  ');
    fill(st.percent);
  } else if (st.type === 'downloaded') {
    line.textContent = `v${st.version} ready: see the banner above.`;
    fill(100);
    $('update-text').textContent = `SlideTistic v${st.version} is ready. Restart to finish updating.`;
    $('update-banner').hidden = false;
  } else if (st.type === 'error') { line.textContent = `Update error: ${st.message}`; bar.hidden = true; }
}

// ---------------------------------------------------------------------------------------------
// Wiring

function wireStatic() {
  $('btn-browse').onclick = $('btn-add').onclick = async () => addPaths(await api.pickFiles());
  $('btn-repair-all').onclick = repairAll;
  $('btn-repair').onclick = () => repair(selected());
  $('btn-cancel').onclick = () => { const d = selected(); if (d) api.cancel(d.id); };
  $('btn-finder').onclick = () => { const d = selected(); if (d) api.showInFolder(d.status === 'repaired' && d.output ? d.output : d.path); };
  $('btn-export').onclick = async () => {
    const d = selected(); if (!d) return;
    const r = await api.exportReport(d.id, d.name);
    if (r.error) toast(r.error); else if (r.path) toast(`Report saved: ${r.path}`);
  };
  $('btn-settings').onclick = openSettings;
  $('btn-slidefluid').onclick = async () => { const r = await api.openSlideFluid(); if (r.error) toast(r.error); };
  $('vep').onclick = (e) => { e.preventDefault(); api.openExternal('https://veproductions.net'); };
  $('update-restart').onclick = () => api.installUpdate();
  $('update-dismiss').onclick = () => { $('update-banner').hidden = true; };
  $('d-update').onclick = () => api.checkForUpdate?.().catch?.(() => { $('d-update-status').textContent = 'Updates work in the installed app, not in development.'; });

  $('tabs').onclick = (e) => { const t = e.target.closest('button')?.dataset.tab; if (t) setTab(t); };

  document.addEventListener('click', (e) => {
    const t = e.target;
    const card = t.closest('.card');
    if (t.closest('[data-remove]')) { const d = S.decks.find((x) => x.id === t.closest('[data-remove]').dataset.remove); if (d) removeDeck(d); return; }
    if (card) { S.sel = card.dataset.id; render(); return; }
    const fs = t.closest('button[data-fs]'); if (fs) { openViewer(Number(fs.dataset.fs)); return; }
    const un = t.closest('[data-undo]'); if (un) { undoSlide(Number(un.dataset.undo)); return; }
    const pp = t.closest('[data-ppt]'); if (pp) { openInPowerPoint(Number(pp.dataset.ppt)); return; }
    const jp = t.closest('[data-jump]'); if (jp) { jumpToSlide(Number(jp.dataset.jump)); return; }
    const sl = t.closest('#alert [data-slide]'); if (sl) { jumpToSlide(Number(sl.dataset.slide)); return; }
    const fl = t.closest('[data-filter]'); if (fl) { S.filter = fl.dataset.filter; render(); return; }
    const md = t.closest('[data-media]'); if (md) { exportMedia(md.dataset.media); return; }
    const url = t.closest('[data-url]'); if (url) { api.openExternal(url.dataset.url); return; }
    if (t.closest('[data-open-output]')) { const d = selected(); if (d?.output) api.showInFolder(d.output); return; }
    if (t.closest('[data-open-mended]')) { const d = selected(); if (d?.output) api.openPath(d.output); return; }
    if (t.closest('[data-close]')) { t.closest('.modal-back').hidden = true; return; }
    if (t.classList.contains('modal-back')) { t.hidden = true; return; }
    const sk = t.closest('.skin'); if (sk) { setSetting('skin', sk.dataset.skin); document.querySelectorAll('.skin').forEach((b) => b.classList.toggle('on', b === sk)); return; }
    const st = t.closest('#set-tabs button'); if (st) {
      document.querySelectorAll('#set-tabs button').forEach((b) => b.classList.toggle('on', b === st));
      ['general', 'fonts', 'look', 'diag'].forEach((k) => { $(`set-${k}`).hidden = k !== st.dataset.set; });
      return;
    }
    if (t.id === 'btn-rescan') { const d = selected(); if (d) scan(d); return; }
  });
  document.addEventListener('dblclick', (e) => { const f = e.target.closest('.frame[data-fs]'); if (f && !S.viewer) openViewer(Number(f.dataset.fs)); });

  document.addEventListener('change', (e) => {
    const t = e.target;
    if (t.dataset.opt) {
      const d = selected(); const preset = presetFor(d);
      const presets = { ...(S.settings.presets || {}) };
      presets[preset] = { ...(presets[preset] || {}), [t.dataset.opt]: { ...((presets[preset] || {})[t.dataset.opt] || {}), [t.dataset.k]: t.checked } };
      setSetting('presets', presets);
      return;
    }
    if (t.id === 'preset-select') { const d = selected(); d.presetOverride = t.value; render(); return; }
    if (t.id === 's-suffix') setSetting('suffix', t.value || ' - mended');
    if (t.id === 's-safe') setSetting('safeZonePct', Math.max(0, Math.min(15, Number(t.value) || 5)));
    if (t.id === 's-quick') setSetting('quickRepair', t.checked);
    if (t.id === 's-crew') setSetting('crewFonts', t.value);
    if (t.id === 's-why') setSetting('showWhy', t.checked);
  });
  $('s-output-pick').onclick = async () => { const p = await api.pickFolder(); if (p) { $('s-output').value = p; setSetting('outputFolder', p); } };
  $('s-output-clear').onclick = () => { $('s-output').value = ''; setSetting('outputFolder', ''); };
  $('s-watch-pick').onclick = async () => { const p = await api.pickFolder(); if (p) { $('s-watch').value = p; setSetting('watchFolder', p); toast(`Watching ${p}`); } };
  $('s-watch-clear').onclick = () => { $('s-watch').value = ''; setSetting('watchFolder', ''); };

  $('v-close').onclick = closeViewer;
  $('v-mode').onclick = () => { S.viewer.mode = S.viewer.mode === 'side' ? 'flip' : 'side'; renderViewer(); };
  $('v-undo').onclick = () => undoSlide(viewerSlide());
  $('v-ppt').onclick = () => openInPowerPoint(viewerSlide());

  // Drag and drop anywhere in the window
  let dragDepth = 0;
  window.addEventListener('dragenter', (e) => { e.preventDefault(); dragDepth++; document.body.classList.add('dragging'); });
  window.addEventListener('dragleave', () => { if (--dragDepth <= 0) { dragDepth = 0; document.body.classList.remove('dragging'); } });
  window.addEventListener('dragover', (e) => e.preventDefault());
  window.addEventListener('drop', (e) => {
    e.preventDefault(); dragDepth = 0; document.body.classList.remove('dragging');
    addPaths([...e.dataTransfer.files].map((f) => api.pathForFile(f)).filter(Boolean));
  });

  document.addEventListener('keydown', onKey);
  document.addEventListener('keyup', (e) => {
    if (S.viewer && e.code === 'Space' && S.viewer.mode === 'flip') { S.viewer.flipShow = 'after'; renderViewer(); }
  });
}

async function exportMedia(kind) {
  const d = selected(); if (!d) return;
  const r = await api.exportMedia(d.path, kind);
  if (r.error) toast(`Export failed: ${r.error}`); else if (r.path) toast(`Saved: ${r.path}`);
}

function onKey(e) {
  const typing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName);
  const mod = isMac ? e.metaKey : e.ctrlKey;
  if (S.viewer) {
    if (e.key === 'Escape') closeViewer();
    else if (e.key === 'ArrowRight') viewerStep(1);
    else if (e.key === 'ArrowLeft') viewerStep(-1);
    else if (e.key.toLowerCase() === 'b') { S.viewer.mode = S.viewer.mode === 'side' ? 'flip' : 'side'; renderViewer(); }
    else if (e.code === 'Space') { e.preventDefault(); if (S.viewer.mode === 'side') S.viewer.mode = 'flip'; if (!e.repeat) { S.viewer.flipShow = 'before'; renderViewer(); } }
    else if (e.key.toLowerCase() === 'u' && !$('v-undo').hidden) undoSlide(viewerSlide());
    else if (e.key.toLowerCase() === 'p') openInPowerPoint(viewerSlide());
    return;
  }
  if (e.key === 'Escape') { document.querySelectorAll('.modal-back').forEach((m) => { m.hidden = true; }); return; }
  if (typing) return;
  if (mod && e.key.toLowerCase() === 'o') { e.preventDefault(); $('btn-add').click(); }
  else if (mod && e.shiftKey && e.key.toLowerCase() === 'r') { e.preventDefault(); repairAll(); }
  else if (mod && e.key.toLowerCase() === 'r') { e.preventDefault(); repair(selected()); }
  else if (mod && e.key.toLowerCase() === 'e') { e.preventDefault(); $('btn-export').click(); }
  else if (mod && e.key === ',') { e.preventDefault(); openSettings(); }
  else if (e.key === '?') $('shortcuts').hidden = false;
  else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    if (!S.decks.length) return;
    e.preventDefault();
    const i = S.decks.findIndex((d) => d.id === S.sel);
    const j = Math.max(0, Math.min(S.decks.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)));
    S.sel = S.decks[j].id; render();
  } else if (e.key === 'Backspace' || e.key === 'Delete') { const d = selected(); if (d) removeDeck(d); }
  else if (['1', '2', '3', '4'].includes(e.key)) setTab(['review', 'findings', 'media', 'options'][Number(e.key) - 1]);
  else if (e.key.toLowerCase() === 'f') {
    const v = (selected()?.review?.data?.visuals || []).find((x) => x.tier < 4) || (selected()?.review?.data?.visuals || [])[0];
    if (v) openViewer(v.slide);
  }
}

init();
