/* SlideTistic renderer. Plain JS, no bundler (SlideFluid pattern). All outside access goes through
   window.slidetistic (preload.js). */
'use strict';

const api = window.slidetistic;
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const isMac = navigator.platform.toLowerCase().includes('mac');

const S = { decks: [], sel: null, tab: 'review', filter: 'all', reviewFilter: 'all', checks: [], settings: {}, info: {}, viewer: null };
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
  if (!isMac) {      // shortcut labels: Ctrl on Windows
    const ctrl = (t) => t.replace(/⇧⌘/g, 'Ctrl+Shift+').replace(/⌘/g, 'Ctrl+').replace(/⌫/g, 'Backspace');
    document.querySelectorAll('kbd').forEach((k) => { k.textContent = ctrl(k.textContent); });
    document.querySelectorAll('.hint').forEach((h) => { h.innerHTML = ctrl(h.innerHTML); });
  }
  $('year').textContent = new Date().getFullYear();
  wireStatic();
  api.onEngineEvent(onEngineEvent);
  api.onWatchFound((files) => addFiles(files, true));
  api.onFontActivation(onFontActivation);
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
    // Keynote (.key, a file or an older folder package) is converted by the engine on a Mac; elsewhere the
    // engine explains how to export it.
    if (f.isDir && f.ext !== '.key') { fail(deck, 'This is a folder of slide images, not a PowerPoint file.'); continue; }
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
  // Compress pictures is chosen per deck from its banner (David 2026-10-11), not per preset.
  if (deck.compress && !fixes.includes('M013')) fixes.push('M013');
  if (deck.compress === false && fixes.includes('M013')) fixes.splice(fixes.indexOf('M013'), 1);
  if (deck.compress && !checks.includes('M013')) checks.push('M013');
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

async function repair(deck, asked = false) {
  if (!deck || deck.status === 'error' || deck.status === 'scanning' || deck.status === 'repairing') return;
  if (!asked && !(await confirmCompress([deck]))) return;
  deck.status = 'repairing'; deck.stage = words().repairing; deck.kind = 'repair'; deck.progress = null;
  deck.partialChecks = []; deck.partialHint = null;
  render();
  const r = await api.repair(deck.id, deck.path, optionsFor(deck));
  deck.output = r.output;
}

async function repairAll() {
  const todo = S.decks.filter((d) => d.status === 'scanned');
  if (!todo.length) { toast('Nothing to repair: add decks, or wait for them to finish checking.'); return; }
  if (!(await confirmCompress(todo))) return;
  todo.forEach((d) => repair(d, true));
  toast(`Repairing ${todo.length} deck${todo.length > 1 ? 's' : ''}, one after another.`);
}

function removeDeck(deck) {
  if (deck.status === 'scanning' || deck.status === 'repairing') api.cancel(deck.id);
  api.discardReview(deck.id);
  const i = S.decks.indexOf(deck);
  S.decks.splice(i, 1);
  if (S.sel === deck.id) S.sel = (S.decks[i] || S.decks[i - 1] || {}).id || null;
  render();
}

const selected = () => S.decks.find((d) => d.id === S.sel);

// ---------------------------------------------------------------------------------------------
// Engine events

const STAGES = { convert: 'Converting from Keynote', scan: 'Checking', fix: 'Fixing', fit: 'Fitting text', render: 'Drawing the slides in PowerPoint',
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
  if (ev.type === 'partial_export_hint') { deck.partialHint = ev; return; }
  if (ev.type === 'partial_export') { deck.partialChecks = (deck.partialChecks || []).concat(ev); return; }
  if (ev.type === 'heartbeat') {
    if (ev.what && ev.what.startsWith('waiting')) { deck.stage = 'Waiting for PowerPoint: another job is using it'; renderBusyOnly(deck); }
    return;
  }
  if (ev.type === 'requeued') { deck.stage = 'Waiting: a repair went first'; deck.progress = null; renderBusyOnly(deck); return; }
  if (ev.type === 'error') { deck.error = ev.message; return; }
  if (ev.type === 'warn') { toast(ev.message); return; }
  if (ev.type === 'review' && ev.partial) {     // findings are in; the slide pictures follow
    deck.version++;
    await loadReview(deck);
    render();
    return;
  }
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
  await Promise.all([loadVotes(deck), loadChecked(deck)]);
  lookupAdobe(deck);          // in the background: the banner says "Checking Adobe Fonts…" meanwhile
}

// ---------------------------------------------------------------------------------------------
// Broken slides: "✓ Checked" marks and the review filter (David 2026-10-12). An operator must be able to
// tell when every critical issue has been looked at, and to see only the big errors when short of time.

const checkedKey = (deck) => {
  const d = deck?.review?.data;
  return d?.tuning?.deck_sha12 ? `${d.tuning.deck_sha12}|${d.output ? 'repaired' : 'checked'}` : null;
};
// A mark counts only while the slide's red findings are the ones that were checked.
const redSig = (v) => v.deck ? v.reds.map((f) => `${f.check_id} ${f.subject}`).sort().join(' | ')
  : (v.after_boxes || []).concat(v.before_boxes || []).filter((b) => b.mode === 'red').map((b) => b.label).sort().join(' | ');
// Reds with no slide (missing fonts, deck settings) are one item to check, so the counter covers them too.
function deckItem(deck) {
  const reds = (deck?.review?.data?.findings || []).filter((f) => f.status === 'red' && !f.slide && !f.informational);
  return reds.length ? { slide: 'deck', tier: 1, deck: true, reds } : null;
}
const isChecked = (deck, v) => { const m = deck.checked?.[v.slide]; return !!m && m.sig === redSig(v); };

async function loadChecked(deck) {
  const key = checkedKey(deck);
  deck.checked = key ? await api.loadChecked(key) : {};
}

// Broken SLIDES only. Deck-wide reds (missing fonts) are the banners' job: a "Whole deck" card repeating them
// crowded the review (David 2026-10-15).
function brokenStats(deck) {
  const reds = (deck?.review?.data?.visuals || []).filter((v) => v.tier === 1);
  return { reds, done: reds.filter((v) => isChecked(deck, v)).length };
}

async function toggleChecked(deck, v) {
  const key = checkedKey(deck);
  if (!key || v.tier !== 1) return;
  const was = deck.checked?.[v.slide];
  const on = !isChecked(deck, v);
  deck.checked = { ...(deck.checked || {}) };
  if (on) deck.checked[v.slide] = { sig: redSig(v) }; else delete deck.checked[v.slide];
  const { reds, done } = brokenStats(deck);
  if (on && done === reds.length) toast('All broken slides checked.');
  refreshChecked(deck);
  const r = await api.setChecked(key, v.slide, on ? redSig(v) : null);
  if (r?.error) {
    deck.checked = { ...deck.checked };
    if (was) deck.checked[v.slide] = was; else delete deck.checked[v.slide];
    refreshChecked(deck);
    toast(`Couldn't save the check mark: ${r.error}`);
  }
}

function refreshChecked(deck) {
  renderQueue();
  if (S.viewer) renderViewer();
  if (deck === selected() && S.tab === 'review') renderReview(deck);
}

function checkedButton(deck, v, big) {
  if (v.tier !== 1) return '';
  const on = isChecked(deck, v);
  return `<button class="btn chk${on ? ' on' : ''}" data-checked="${v.slide}" title="Mark this broken slide as checked (C)">${on ? '✓ Checked' : '☐ Mark checked'}${big ? ' <kbd>C</kbd>' : ''}</button>`;
}

const REVIEW_FILTERS = [['all', 'Everything'], ['look', 'Broken + Look at'], ['broken', 'Broken only']];
const inFilter = (v) => S.reviewFilter === 'broken' ? v.tier === 1 : S.reviewFilter === 'look' ? v.tier === 1 || v.tier === 3 : true;

function brokenStrip(deck) {
  const { reds, done } = brokenStats(deck);
  const filters = REVIEW_FILTERS.map(([k, l]) => `<button data-rfilter="${k}" class="${S.reviewFilter === k ? 'on' : ''}">${l}</button>`).join('');
  let state;
  if (!reds.length) state = '<span class="ok">✓ No broken slides</span>';
  else if (done === reds.length) state = '<span class="ok">✓ Every broken slide checked</span>';
  else state = `<span class="bad">✕ ${reds.length} broken slide${reds.length === 1 ? '' : 's'} · ${done} checked off</span>`;
  return `<div class="broken-strip ${!reds.length || done === reds.length ? 'clear' : ''}">${state}<span class="grow"></span>` +
         `<div class="seg" title="Show only some slides (R: Broken only)">${filters}</div></div>`;
}

// ---------------------------------------------------------------------------------------------
// Tuning votes (David 2026-10-11): 👍/👎 on each changed slide, behind Settings › Diagnostics › Tuning
// mode. `slidetistic tune` turns the votes into proposed rules; nothing changes until David approves.

const REASONS = [['not_worth', 'Not worth it'], ['worse', 'Made it worse'], ['wrong_fix', 'Wrong kind of fix'],
                 ['false_flag', "Shouldn't have flagged it"]];
const tuningOn = () => !!S.settings.tuningMode;
const votable = (deck, v) => tuningOn() && !!deck?.review?.data?.output && !!deck.review.data.tuning
  && !v.undone && !v.looks_same && (v.tuning || []).length > 0;
const voteKey = (v) => `${v.slide}|${v.tuning_sig}`;
const voteOf = (deck, v) => deck.votes?.[voteKey(v)];
const baseName = (p) => String(p || '').split(/[\\/]/).pop();

async function loadVotes(deck) {
  const sha = deck?.review?.data?.tuning?.deck_sha12;
  if (!tuningOn() || !sha) return;
  const r = await api.loadVotes(sha);
  deck.votes = Object.fromEntries((r.deck || []).map((x) => [`${x.slide}|${x.tuning_sig}`, x]));
  S.voteTotals = { total: r.total, up: r.up, dir: r.dir };
}

function voteStats(deck) {
  const vs = (deck?.review?.data?.visuals || []).filter((v) => votable(deck, v));
  return { votable: vs, done: vs.filter((v) => voteOf(deck, v)).length };
}

async function castVote(deck, v, vote, reason = null) {
  const data = deck.review.data;
  const key = voteKey(v);
  const prev = deck.votes?.[key];
  const rec = { deck_sha12: data.tuning.deck_sha12, deck: baseName(data.input), slide: v.slide, vote, reason,
                tuning_sig: v.tuning_sig, changes: v.tuning, diff_pct: v.diff_pct, tier: v.tier,
                gates_hash: data.tuning.gates_hash, thresholds: data.tuning.thresholds, engine: data.engine,
                source: data.source?.kind || null };
  // Optimistic: the vote shows at once; it's put back if saving fails.
  const totals = S.voteTotals || { total: 0, up: 0 };
  const adjust = (r, sign) => { if (r) { totals.total += sign; if (r.vote === 'up') totals.up += sign; } };
  deck.votes = { ...(deck.votes || {}) };
  adjust(prev, -1);
  if (vote === 'clear') delete deck.votes[key]; else { deck.votes[key] = rec; adjust(rec, 1); }
  S.voteTotals = totals;
  refreshVotes(deck);
  const r = await api.vote(rec);
  if (r?.error) {
    adjust(deck.votes[key], -1);
    if (prev) { deck.votes[key] = prev; adjust(prev, 1); } else delete deck.votes[key];
    refreshVotes(deck);
    toast(`Vote not saved: ${r.error}`);
  }
}

function refreshVotes(deck) {
  if (S.viewer) renderViewer();
  if (deck === selected() && S.tab === 'review') renderReview(deck);
}

function voteControls(deck, v, big) {
  const cur = voteOf(deck, v);
  const up = `<button class="btn vote up${cur?.vote === 'up' ? ' on' : ''}" data-vote="up" data-vslide="${v.slide}" title="Good change (Y or ↑)">👍${big ? ' Good <kbd>Y</kbd>' : ''}</button>`;
  const down = `<button class="btn vote down${cur?.vote === 'down' ? ' on' : ''}" data-vote="down" data-vslide="${v.slide}" title="Bad change (N or ↓; 1–4 adds why)">👎${big ? ' Bad <kbd>N</kbd>' : ''}</button>`;
  const reasons = (big || cur?.vote === 'down') ? REASONS.map(([k, label], i) =>
    `<button class="rchip${cur?.reason === k ? ' on' : ''}" data-reason="${k}" data-vslide="${v.slide}">${big ? `<kbd>${i + 1}</kbd> ` : ''}${label}</button>`).join('') : '';
  return `<span class="votes">${up}${down}${reasons ? `<span class="reasons">${reasons}</span>` : ''}</span>`;
}

function tuningLine(deck) {
  const { votable: vs, done } = voteStats(deck);
  const t = S.voteTotals;
  const all = t && t.total ? ` · all decks: ${t.total} vote${t.total > 1 ? 's' : ''}, ${Math.round(100 * t.up / t.total)}% 👍` : '';
  return `This deck: ${done} of ${vs.length} changed slide${vs.length === 1 ? '' : 's'} voted${all}`;
}

function nextUnvoted(deck, fromIdx) {
  const visuals = deck.review.data.visuals || [];
  for (let k = 1; k <= visuals.length; k++) {
    const i = (fromIdx + k) % visuals.length;
    if (votable(deck, visuals[i]) && !voteOf(deck, visuals[i])) return i;
  }
  return -1;
}

function voteInViewer(vote, reason = null, advance = false) {
  const deck = selected();
  const v = (deck?.review?.data?.visuals || [])[S.viewer?.idx];
  if (!v || !votable(deck, v)) return;
  castVote(deck, v, vote, reason);
  if (!advance) return;
  const next = nextUnvoted(deck, S.viewer.idx);
  if (next < 0) { toast('Every changed slide in this deck has a vote. Thank you!'); return; }
  S.viewer.idx = next;
  S.viewer.flipShow = 'after';
  renderViewer();
}

function startVoting() {
  const deck = selected();
  if (!deck?.review?.data) return;
  const visuals = deck.review.data.visuals || [];
  let i = nextUnvoted(deck, -1);
  if (i < 0) i = visuals.findIndex((v) => votable(deck, v));
  if (i < 0) { toast('No changed slides to vote on in this deck.'); return; }
  openViewer(visuals[i].slide);
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

// Counts are slides, like the review (2.2, review 2026-10-13): "15 findings" over 2 slides read as 15 jobs. Findings
// with no slide count once as "the deck". Offers (compress pictures) and low-priority notes aren't counted.
function slideCounts(data) {
  const slides = (pred) => new Set((data?.findings || []).filter((f) => !f.informational && pred(f)).map((f) => f.slide || 'deck')).size;
  return {
    fixed: slides((f) => f.status === 'green_fixed'),
    look: slides((f) => f.status === 'yellow' && !f.evidence?.note && f.check_id !== 'M013'),
    broken: slides((f) => f.status === 'red' || f.status === 'tool_error'),
  };
}

function summaryChips(data, short = false) {
  const w = words(), c = slideCounts(data);
  const label = (n, word) => (short ? '' : ` ${n === 1 ? 'slide' : 'slides'} ${word}`);
  const tip = 'Slides; problems that aren\'t on one slide (fonts, deck settings) count once as the deck';
  return `<span class="chip g" title="${tip}">✓ ${c.fixed}${label(c.fixed, w.fixed)}</span>` +
         `<span class="chip y" title="${tip}">! ${c.look}${label(c.look, w.look)}</span>` +
         `<span class="chip r" title="${tip}">✕ ${c.broken}${short ? '' : ` ${w.broken}`}</span>`;
}

// Media is the operator's biggest pre-show job (download, offline, re-embed), so it gets its own signal.
// Level: red = won't play offline as is; amber = files to fetch or keep with the deck; blue = all embedded.
function mediaSummary(data) {
  const fs = data?.findings || [];
  const by = (id, status) => fs.filter((f) => f.check_id === id && (!status || f.status === status));
  const inv = by('M002');
  const slides = (list) => [...new Set(list.map((f) => f.slide).filter(Boolean))].sort((a, b) => a - b);
  const issues = [];
  const online = by('M005'), missing = by('M003', 'red'), nearby = by('M003', 'yellow'), links = by('M006');
  if (online.length) issues.push({ lvl: 'r', n: online.length, what: `online video${online.length > 1 ? 's' : ''} to download and embed (won't play offline)`, slides: slides(online) });
  if (missing.length) issues.push({ lvl: 'r', n: missing.length, what: `linked file${missing.length > 1 ? 's' : ''} missing: get ${missing.length > 1 ? 'them' : 'it'} and embed`, slides: slides(missing) });
  if (links.length) issues.push({ lvl: 'y', n: links.length, what: `video link${links.length > 1 ? 's' : ''} in the slides or notes to download`, slides: slides(links) });
  if (nearby.length) issues.push({ lvl: 'y', n: nearby.length, what: `linked file${nearby.length > 1 ? 's' : ''} next to the deck: copy together or embed`, slides: slides(nearby) });
  const videos = inv.filter((f) => f.evidence?.kind === 'video').length;
  const audio = inv.filter((f) => f.evidence?.kind === 'audio').length;
  if (!issues.length && !inv.length) return null;
  const lvl = issues.some((i) => i.lvl === 'r') ? 'r' : issues.length ? 'y' : 'b';
  const parts = [videos && `${videos} video${videos > 1 ? 's' : ''}`, audio && `${audio} audio clip${audio > 1 ? 's' : ''}`].filter(Boolean);
  const embedded = inv.filter((f) => !f.evidence?.linked).length;
  const inventory = parts.length ? `${parts.join(', ')}${embedded === inv.length ? ', all embedded' : ''}` : '';
  return { lvl, issues, inventory, count: inv.length + online.length + links.length, slides: slides(inv) };
}

// Fonts (David 2026-10-12, modelled on Media): what's missing, where it's shown, and what Get fonts can install.
function fontSummary(data) {
  const rows = data?.fonts || [];
  const red = rows.filter((r) => r.level === 'r'), yellow = rows.filter((r) => r.level === 'y');
  if (!red.length && !yellow.length) return null;
  const free = rows.filter((r) => r.free && r.level !== 'n');
  const slides = [...new Set(red.concat(yellow).flatMap((r) => r.slides))].sort((a, b) => a - b);
  return { lvl: red.length ? 'r' : 'y', red, yellow, free, slides, count: red.length + yellow.length,
           unused: rows.filter((r) => r.level === 'n').length };
}

const AA = '<svg class="spk" viewBox="0 0 16 16" aria-hidden="true"><text x="0.5" y="12.5" font-size="12" font-weight="700" fill="currentColor" font-family="Georgia, serif">Aa</text></svg>';

function fontChip(f) {
  const tip = `${f.red.length ? `${f.red.length} font${f.red.length > 1 ? 's' : ''} missing on show machines. ` : ''}` +
              `${f.yellow.length ? `${f.yellow.length} to check. ` : ''}${f.free.length ? `${f.free.length} free to install.` : ''}`;
  return `<span class="chip media ${f.lvl}" title="${esc(tip.trim())}">${AA}${f.count}</span>`;
}

async function getFonts(deck, families) {
  if (!deck || !families.length || deck.fontsBusy) return;
  deck.fontsBusy = families;
  render();
  const r = await api.getFonts(deck.path, families);
  deck.fontsBusy = null;
  const fontsDone = (r.events || []).filter((e) => e.type === 'font');
  const failed = fontsDone.filter((e) => !e.ok);
  if (r.error) toast(`Couldn't get fonts: ${r.error}`);
  else if (failed.length) toast(failed.map((e) => e.message).join(' · '));
  else if (fontsDone.length) toast(`Installed ${fontsDone.map((e) => e.family).join(', ')}. Restart PowerPoint to use ${fontsDone.length > 1 ? 'them' : 'it'}; checking the deck again.`);
  const ok = fontsDone.filter((e) => e.ok);
  if (ok.length) {
    resolve(deck, families.length === 1 && isNoteFont(deck, families[0]) ? `font-note:${families[0]}` : 'fonts-free',
      `${ok.map((e) => e.family).join(', ')} installed`, ok.map((e) => e.message).join('\n') + '\nRestart PowerPoint to use them.');
  }
  deck.fontsAsk = null;
  render();
  if (fontsDone.some((e) => e.ok)) scan(deck);
}

const isNoteFont = (deck, family) => (deck.review?.data?.fonts || []).some((r) => r.family === family && r.level === 'y');

async function collectFonts(deck) {
  if (!deck || deck.fontsCollecting) return;
  deck.fontsCollecting = true;
  renderFonts(deck);
  const r = await api.collectFonts(deck.path);
  deck.fontsCollecting = false;
  renderFonts(deck);
  const got = (r.events || []).filter((e) => e.type === 'font');
  const missing = got.filter((e) => /not found|failed|not available/.test(e.how));
  if (r.error || !r.folder) toast(`Couldn't collect fonts: ${r.error || 'no folder made'}`);
  else toast(`${got.length - missing.length} of ${got.length} fonts in "${r.folder.split(/[\\/]/).pop()}"${missing.length ? ` (${missing.length} not found: see FONTS.txt)` : ''}.`);
  if (r.folder && !r.error) {
    resolve(deck, 'fonts-collect', `${got.length - missing.length} font${got.length - missing.length === 1 ? '' : 's'} collected next to the deck`,
      `In ${r.folder}: ${got.map((e) => `${e.name} (${e.how})`).join(', ')}. FONTS.txt lists where each came from.`);
    render();
  }
}

const SLIDEFLUID_RELEASES = 'https://github.com/Horton619/slidefluid/releases/latest';

const SPEAKER = '<svg class="spk" viewBox="0 0 16 16" aria-hidden="true"><path d="M2 6h3l4-3v10L5 10H2z" fill="currentColor"/>' +
  '<path d="M11 5.5a3.5 3.5 0 0 1 0 5M12.8 3.6a6 6 0 0 1 0 8.8" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>';

function mediaChip(m) {
  const tip = [m.inventory && `Media: ${m.inventory}.`, ...m.issues.map((i) => `${i.n} ${i.what}.`)].filter(Boolean).join(' ');
  return `<span class="chip media ${m.lvl}" title="${esc(tip)}">${SPEAKER}${m.count}</span>`;
}

// ---------------------------------------------------------------------------------------------
// Action banners (David 2026-10-13, docs/mockups/status-strip.html "After"). Each alert is one line with the
// action that resolves it; once resolved it turns into a small green line, full detail on hover. Alerts are
// built from the review each time; what the operator did (resolved, dismissed) lives on the deck.

const SOURCE_LABEL = { canva: 'Canva export', google: 'Google Slides export', keynote: 'Keynote export', pdf: 'Slides are pictures' };

function renderSource(deck) {
  const data = deck.review?.data;
  const src = data?.source;
  const kind = data?.converted_from ? 'keynote' : src?.kind;
  const el = $('source');
  el.hidden = !(kind && SHOUT[kind]);
  if (el.hidden) return;
  const why = data?.converted_from
    ? `Converted from Keynote by Keynote itself. Check builds and Magic Move transitions (they become plain fades) and fonts like Avenir. From ${data.converted_from}`
    : src.message;
  el.innerHTML = `${esc(data?.converted_from ? 'Converted from Keynote' : SOURCE_LABEL[kind])}<span class="tip"><b>${esc(SHOUT[kind][0])}</b> ` +
    `${esc(SHOUT[kind][1])}<span class="dim">Why: ${esc(why)}</span></span>`;
}

// "slides 35–37, 40" with each number a link to the slide.
function slideRefs(nums) {
  const list = [...new Set(nums)].filter(Boolean).sort((a, b) => a - b);
  if (!list.length) return '';
  const parts = [];
  for (let i = 0; i < list.length; i++) {
    let j = i;
    while (j + 1 < list.length && list[j + 1] === list[j] + 1) j++;
    const link = (n) => `<a data-slide="${n}">${n}</a>`;
    parts.push(j > i + 1 ? `${link(list[i])}–${link(list[j])}` : j === i + 1 ? `${link(list[i])}, ${link(list[j])}` : link(list[i]));
    i = j;
  }
  return `slide${list.length > 1 ? 's' : ''} ${parts.join(', ')}`;
}

const nameList = (rows, max = 3) => {
  const n = rows.map((r) => esc(r.family));
  return n.length <= max ? n.join(n.length === 2 ? ' and ' : ', ') : `${n.slice(0, max).join(', ')} and ${n.length - max} more`;
};
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

// Each banner: { key, lvl: r|y|n, icon, msg (html), actions: [{ act, label, primary, arg }], dismiss }
function bannerList(deck) {
  const data = deck.review?.data;
  if (!data) return [];
  const out = [];
  const findings = data.findings || [];

  const off = findings.filter((f) => f.status === 'red' && f.subject === 'off-slide' && f.slide).map((f) => f.slide);
  if (off.length) {
    const { reds, done } = brokenStats(deck);
    if (reds.length && done === reds.length) deck.resolved = { ...deck.resolved, offslide: { short: 'Broken slides checked', detail: `Text ran off ${slideRefs(off).replace(/<[^>]+>/g, '')}; every broken item is marked checked.` } };
    else out.push({ key: 'offslide', lvl: 'r', icon: '✕', msg: `<b>Text runs off the slide</b> on ${slideRefs(off)}. Fix before the show.`,
                    actions: [{ act: 'broken', label: 'Show broken slides <kbd>R</kbd>' }] });
  }

  const rows = data.fonts || [];
  const red = rows.filter((r) => r.level === 'r');
  const free = red.filter((r) => r.free && !r.here);
  const collectable = red.filter((r) => r.here);
  const canvaOnly = red.filter((r) => !r.free && !r.here && /^Canva-only/.test(r.status));
  const rest = red.filter((r) => !r.free && !r.here && !canvaOnly.includes(r));
  const onAdobe = rest.filter((r) => deck.adobe?.[r.family]?.info);
  const nowhere = rest.filter((r) => !onAdobe.includes(r));
  const busy = deck.fontsBusy;
  // Get fonts asks right here, in the banner that was clicked (David 2026-10-15: jumping to the Fonts tab, with the
  // question in a table row below the fold, looked like nothing happened).
  if (deck.fontsAskBanner && deck.fontsAsk?.length && !busy) {
    const rowsAsked = rows.filter((r) => deck.fontsAsk.includes(r.family) && r.free);
    const what = rowsAsked.map((r) => `${esc(r.family)} (${esc((r.free.variants || []).map((v) => ({ 100: 'Thin', 200: 'ExtraLight', 300: 'Light', 400: 'Regular', 500: 'Medium', 600: 'SemiBold', 700: 'Bold', 800: 'ExtraBold', 900: 'Black' })[v[0]] || v[0]).join(', '))})`).join(', ');
    const from = [...new Set(rowsAsked.map((r) => (r.free.publisher ? `${r.free.publisher}: ${r.free.license || 'free download'}` : 'Fontsource / Google Fonts: open licence')))].join('; ');
    out.push({ key: deck.fontsAskKey || 'fonts-free', lvl: 'y', icon: AA,
      msg: `<b>Install ${what} for you on this ${isMac ? 'Mac' : 'PC'}?</b> <span class="dim">${esc(from)}. No admin rights; restart PowerPoint afterwards.</span>`,
      actions: [{ act: 'fonts-install', label: 'Install', primary: true }, { act: 'fonts-cancel', label: 'Cancel' }] });
  }
  if (free.length && !(deck.fontsAskBanner && deck.fontsAsk?.length && !busy)) {
    out.push({ key: 'fonts-free', lvl: 'r', icon: AA,
      msg: free.length === 1 ? `<b>${esc(free[0].family)} is missing</b>${free[0].slides.length ? ` (${slideRefs(free[0].slides)})` : ''} and it's a free download.`
        : `<b>${free.length} missing fonts are free downloads</b>: ${nameList(free)}.`,
      actions: [{ act: 'get-fonts', primary: true, disabled: !!busy,
                  label: busy ? 'Installing…' : free.length === 1 ? `Get ${esc(free[0].family)}` : `Get ${free.length} free fonts` }] });
  }
  if (collectable.length) {
    out.push({ key: 'fonts-collect', lvl: 'r', icon: AA,
      msg: `<b>${plural(collectable.length, 'font can', 'fonts can')} be collected</b> (installed on this computer or in your Creative Cloud): ${nameList(collectable)}.`,
      actions: [{ act: 'collect', label: deck.fontsCollecting ? 'Collecting…' : `Collect ${plural(collectable.length, 'font', 'fonts')}`, disabled: !!deck.fontsCollecting }] });
  }
  if (onAdobe.length) {
    const act = deck.activating;
    out.push({ key: 'fonts-adobe', lvl: 'r', icon: AA,
      msg: `<b>${plural(onAdobe.length, 'font is', 'fonts are')} on Adobe Fonts</b>: ${nameList(onAdobe)}. Activate ${onAdobe.length > 1 ? 'them' : 'it'}, then collect.` +
        (act ? ` <span class="dim">${esc(act.current || '…')} (${act.index + 1} of ${act.total}): click Add on its page in your browser; the next one opens by itself.</span>` : ''),
      actions: act ? [{ act: 'adobe', label: 'Open page again ↗' }, { act: 'adobe-next', label: 'Next font' }, { act: 'adobe-stop', label: 'Stop' }]
        : [{ act: 'adobe', label: 'Activate in Adobe Fonts ↗' }] });
  }
  if (canvaOnly.length) {
    out.push({ key: 'fonts-canva', lvl: 'r', icon: AA,
      msg: `<b>${plural(canvaOnly.length, 'Canva-only font', 'Canva-only fonts')}</b>: ${nameList(canvaOnly)}. No other computer has ${canvaOnly.length > 1 ? 'them' : 'it'}; repair swaps in a stand-in.`,
      actions: [{ act: 'tab', arg: 'fonts', label: 'Fonts tab' }] });
  }
  if (nowhere.length) {
    const pending = deck.adobe === undefined;
    out.push({ key: 'fonts-missing', lvl: 'r', icon: AA,
      msg: `<b>${plural(nowhere.length, 'font is', 'fonts are')} missing</b> and not a free download: ${nameList(nowhere)}.` +
        (pending ? ' <span class="dim">Checking Adobe Fonts…</span>' : ' Ask whoever made the deck for the files.'),
      actions: [{ act: 'tab', arg: 'fonts', label: 'Fonts tab' }] });
  }
  const yellow = rows.filter((r) => r.level === 'y');
  if (yellow.length === 1 || yellow.length === 2) {
    for (const r of yellow) {
      out.push({ key: `font-note:${r.family}`, lvl: 'n', icon: 'i', dismiss: true,
        msg: `${esc(r.family)}: ${esc(r.status)}.`,
        actions: r.free ? [{ act: 'get-font', arg: r.family, label: `Get ${esc(r.family)}`, disabled: !!busy }] : [] });
    }
  } else if (yellow.length) {
    out.push({ key: 'font-notes', lvl: 'y', icon: AA, dismiss: true,
      msg: `<b>${yellow.length} fonts to check</b>: ${yellow.slice(0, 3).map((r) => `${esc(r.family)} (${esc(r.status)})`).join(', ')}${yellow.length > 3 ? '…' : ''}`,
      actions: [{ act: 'tab', arg: 'fonts', label: 'Fonts tab' }] });
  }

  const by = (id, status) => findings.filter((f) => f.check_id === id && (!status || f.status === status));
  const links = by('M005').concat(by('M006'));
  if (links.length === 1) {
    const f = links[0];
    out.push({ key: 'media-link', lvl: f.check_id === 'M005' ? 'r' : 'y', icon: SPEAKER,
      msg: `<b>1 video link to download</b> (${slideRefs([f.slide])}${f.evidence?.site ? `, ${esc(f.evidence.site)}` : ''}). Download it, then embed it in PowerPoint.`,
      actions: [{ act: 'link', arg: f.evidence?.url || f.subject, label: 'Open video link ↗' }] });
  } else if (links.length) {
    out.push({ key: 'media-links', lvl: links.some((f) => f.check_id === 'M005') ? 'r' : 'y', icon: SPEAKER,
      msg: `<b>${links.length} video links to download</b> (${slideRefs(links.map((f) => f.slide))}). Download each, then embed it in PowerPoint.`,
      actions: [{ act: 'tab', arg: 'media', label: 'Media tab: links' }] });
  }
  const missing = by('M003', 'red'), nearby = by('M003', 'yellow');
  if (missing.length) {
    out.push({ key: 'media-missing', lvl: 'r', icon: SPEAKER,
      msg: `<b>${plural(missing.length, 'linked media file is', 'linked media files are')} missing</b> (${slideRefs(missing.map((f) => f.slide))}). Get ${missing.length > 1 ? 'them' : 'it'} and embed.`,
      actions: [{ act: 'tab', arg: 'media', label: 'Media tab' }] });
  }
  if (nearby.length) {
    out.push({ key: 'media-nearby', lvl: 'y', icon: SPEAKER,
      msg: `<b>${plural(nearby.length, 'linked media file sits', 'linked media files sit')} next to the deck</b> (${slideRefs(nearby.map((f) => f.slide))}): copy ${nearby.length > 1 ? 'them' : 'it'} with the deck, or embed.`,
      actions: [{ act: 'tab', arg: 'media', label: 'Media tab' }] });
  }
  const m = mediaSummary(data);
  if (m && m.lvl === 'b' && m.inventory) {
    out.push({ key: 'media-inventory', lvl: 'n', icon: SPEAKER, dismiss: true,
      msg: `${esc(m.inventory)} (${slideRefs(m.slides)}). Check ${m.count > 1 ? 'they play' : 'it plays'} on the show machine.`, actions: [] });
  }

  // Changed-slide export (3.10): offered only when this repair shows it would save real time.
  if (deck.partialHint && (S.settings.partialExport || 'off') === 'off') {
    out.push({ key: 'partial-export', lvl: 'n', icon: '⏱', dismiss: true,
      msg: `Repairing this deck could take about <b>${deck.partialHint.seconds} s less</b>: PowerPoint can draw only the slides each layout round changed.`,
      actions: [{ act: 'partial-try', label: 'Try it (check mode)' }] });
  }
  const pc = deck.partialChecks || [];
  if (pc.length && deck.status === 'repaired') {
    const bad = pc.filter((e) => e.mismatch.length);
    deck.resolved = { ...deck.resolved, 'partial-export': bad.length
      ? { short: `Changed-slide export disagreed on ${bad.length} round${bad.length > 1 ? 's' : ''} (full export used)`, detail: 'Slides: ' + bad.flatMap((e) => e.mismatch).join(', ') + '. Leave it on Check or Off, and tell David.' }
      : { short: `Changed-slide export matched the full export (${pc.length} round${pc.length > 1 ? 's' : ''})`, detail: 'Check mode drew each round both ways and they agreed. Once a few decks agree, set it to On in Settings › Diagnostics for the speed.' } };
  }

  const cf = findings.find((f) => f.check_id === 'M013');
  if (cf?.status === 'green_fixed') {
    deck.resolved = { ...deck.resolved, compress: { short: `Pictures compressed: ${data.input_mb} MB → ${data.output_mb ?? '?'} MB`,
      detail: 'Sized for a 1080p screen with cropped areas deleted, like PowerPoint\'s Compress Pictures at 150 ppi.' } };
  }
  return out;
}

function actionBanners(deck) {
  // A resolved alert shows as its green line even while the review still lists the problem (a collected
  // font is still missing on the show machines; an opened link is still in the slides).
  const resolved = deck.resolved || {};
  const live = bannerList(deck).filter((b) => !(deck.dismissed || []).includes(b.key) && !resolved[b.key]);
  const done = Object.entries(deck.resolved || {});
  const lead = deck.status === 'repaired' ? live.find((b) => b.actions.length)?.actions[0] : null;
  const button = (a) => `<button class="btn sm${a === lead ? ' p' : ''}" data-act="${a.act}"${a.arg ? ` data-arg="${esc(a.arg)}"` : ''}${a.disabled ? ' disabled' : ''}>${a.label}</button>`;
  return live.map((b) => `<div class="abn ${b.lvl}" data-key="${esc(b.key)}"><span class="ic">${b.icon}</span><span class="msg">${b.msg}</span>` +
      b.actions.map(button).join('') + (b.dismiss ? `<button class="icon" data-act="dismiss" aria-label="Dismiss" title="Dismiss">✕</button>` : '') + '</div>').join('') +
    done.map(([k, r]) => `<div class="abn done small" data-key="${esc(k)}" title="${esc(r.detail || r.short)}"><span class="ic">✓</span><span class="msg">${esc(r.short)}</span></div>`).join('');
}

function bannerAction(deck, el) {
  if (!deck) return;
  const { act, arg } = el.dataset;
  const key = el.closest('.abn')?.dataset.key;
  if (act === 'broken') { if (S.tab !== 'review') setTab('review'); setReviewFilter('broken'); return; }
  if (act === 'tab') { setTab(arg); return; }
  if (act === 'collect') { collectFonts(deck); return; }
  if (act === 'adobe') { activateAdobe(deck); return; }
  if (act === 'adobe-next') { api.activateNext(); return; }
  if (act === 'adobe-stop') { api.activateStop(); return; }
  if (act === 'get-fonts' || act === 'get-font') {
    // Asks first, with each font's source and licence (never accepted on David's behalf).
    deck.fontsAsk = act === 'get-font' ? [arg]
      : (deck.review.data.fonts || []).filter((r) => r.level === 'r' && r.free && !r.here).map((r) => r.family);
    deck.fontsAskBanner = true;
    deck.fontsAskKey = act === 'get-font' ? `font-note:${arg}` : 'fonts-free';
    render();
    return;
  }
  if (act === 'fonts-install') { const fams = deck.fontsAsk || []; deck.fontsAsk = null; deck.fontsAskBanner = false; getFonts(deck, fams); return; }
  if (act === 'fonts-cancel') { deck.fontsAsk = null; deck.fontsAskBanner = false; render(); return; }
  if (act === 'link') {
    api.openExternal(arg);
    const f = (deck.review.data.findings || []).find((x) => ['M005', 'M006'].includes(x.check_id));
    resolve(deck, key, 'Video link opened', `Opened ${arg} in your browser. Download it, embed it in PowerPoint` +
      `${f?.slide ? `, then mark slide ${f.slide} checked` : ''}.`);
    render();
    return;
  }
  if (act === 'partial-try') {
    setSetting('partialExport', 'check');
    resolve(deck, key, 'Changed-slide export: check mode on', 'Settings › Diagnostics › Export only changed slides is on Check: the next repairs draw both ways and compare.');
    render();
    return;
  }
  if (act === 'dismiss') { deck.dismissed = [...(deck.dismissed || []), key]; render(); }
}

function resolve(deck, key, short, detail) {
  deck.resolved = { ...(deck.resolved || {}), [key]: { short, detail } };
}

// Adobe Fonts: asked once per review for the missing fonts nothing else can supply.
async function lookupAdobe(deck) {
  const rows = (deck.review?.data?.fonts || []).filter((r) => r.level === 'r' && !r.free && !r.here && !/^Canva-only/.test(r.status));
  if (!rows.length) { deck.adobe = {}; return; }
  const families = rows.map((r) => r.family);
  if (deck.adobe && families.every((f) => f in deck.adobe)) return;
  deck.adobe = undefined;
  const got = await api.adobeFonts(families);
  deck.adobe = got || {};
  if (selected() === deck) render();
}

async function activateAdobe(deck) {
  const rows = (deck.review?.data?.fonts || []).filter((r) => r.level === 'r' && deck.adobe?.[r.family]?.info);
  const items = rows.map((r) => ({ family: r.family, link: deck.adobe[r.family].info.link }));
  const r = await api.activateFonts(deck.id, items);
  if (r?.error) { toast(`Couldn't open Adobe Fonts: ${r.error}`); return; }
  if (r?.ok) toast('Opened in your browser: click "Add" on the font\'s page. The next font opens by itself once Creative Cloud has it.');
}

function onFontActivation(ev) {
  const deck = S.decks.find((d) => d.id === ev.deckId);
  if (!deck) return;
  if (ev.finished) {
    deck.activating = null;
    if (ev.adobeOnly?.length) {
      resolve(deck, 'fonts-adobe-only', `${ev.adobeOnly.join(', ')}: Adobe apps only, not PowerPoint`,
        `Creative Cloud added ${ev.adobeOnly.join(', ')} for Adobe's own apps only, so PowerPoint can't use ${ev.adobeOnly.length > 1 ? 'them' : 'it'}. ` +
        'Ask the presenter for the font files, or swap the font.');
      toast(`${ev.adobeOnly.join(', ')} ${ev.adobeOnly.length > 1 ? 'were' : 'was'} added for Adobe apps only; PowerPoint can't use ${ev.adobeOnly.length > 1 ? 'them' : 'it'}.`);
    }
    if (ev.done.length) {
      delete deck.resolved?.['fonts-collect'];       // newly activated fonts are collectable now
      resolve(deck, 'fonts-adobe', `${ev.done.join(', ')} activated`,
        `Activated from Adobe Fonts through Creative Cloud: ${ev.done.join(', ')}.${ev.done.length < ev.total ? ` ${ev.total - ev.done.length} not added.` : ''} Collect fonts copies them next to the deck.`);
      toast(`${ev.done.join(', ')} ${ev.done.length > 1 ? 'are' : 'is'} on this computer now. Checking the deck again.`);
      scan(deck);
    } else render();
    return;
  }
  deck.activating = ev;
  if ((ev.done.length || ev.adobeOnly?.length) && ev.current) toast(`Next: ${ev.current}.`);
  if (selected() === deck) render();
}

// Compression is offered when Repair is clicked (David 2026-10-13), for every deck in that repair that could
// shrink and hasn't been asked yet.
function compressOffer(deck) {
  const cf = (deck.review?.data?.findings || []).find((f) => f.check_id === 'M013' && f.status === 'yellow');
  if (!cf || deck.compress !== undefined) return null;
  const m = /from ([\d.,]+ [KMG]B) to about ([\d.,]+ [KMG]B)/.exec(cf.message || '');
  return m ? `${m[1]} → about ${m[2]}` : '';
}

function confirmCompress(decks) {
  const ask = decks.map((d) => [d, compressOffer(d)]).filter(([, o]) => o !== null);
  if (!ask.length) return Promise.resolve(true);
  return new Promise((done) => {
    $('cm-rows').innerHTML = ask.map(([d, o], i) => `<label class="cm-row"><input type="checkbox" data-cm="${i}" checked> ` +
      `${esc(d.name)}<span class="dim">${esc(o)}</span></label>`).join('');
    const modal = $('compress-modal');
    modal.hidden = false;
    const finish = (choice) => {
      observer.disconnect();
      modal.hidden = true;
      if (choice !== null) ask.forEach(([d], i) => { d.compress = choice && !!document.querySelector(`[data-cm="${i}"]`)?.checked; });
      done(choice !== null);
    };
    // Esc or a click outside closes it (no repair): watch for the generic modal close.
    const observer = new MutationObserver(() => { if (modal.hidden) finish(null); });
    observer.observe(modal, { attributes: true, attributeFilter: ['hidden'] });
    $('cm-yes').onclick = () => finish(true);
    $('cm-no').onclick = () => finish(false);
    $('cm-yes').focus();
  });
}

function renderQueue() {
  $('queue-count').textContent = S.decks.length ? `${S.decks.length} deck${S.decks.length > 1 ? 's' : ''}` : '';
  $('queue').innerHTML = S.decks.map((d) => {
    const sum = d.review?.data?.summary;
    let body;
    if (d.status === 'error') body = `<div class="chips"><span class="chip r">✕ ${esc(d.error)}</span></div>`;
    else if (d.status === 'scanning' || d.status === 'repairing' || d.status === 'queued')
      body = `<div class="chips"><span class="chip v">${esc(d.status === 'queued' ? 'Waiting…' : d.stage)}</span></div><div class="mini-bar"><i></i></div>`;
    else if (sum) {
      const m = mediaSummary(d.review.data);
      let chips = summaryChips(d.review.data, true);
      const { reds, done } = brokenStats(d);
      if (reds.length && done === reds.length) chips = chips.replace('<span class="chip r">✕', '<span class="chip r cleared" title="Every broken item has been checked">✓');
      const fo = fontSummary(d.review.data);
      body = `<div class="chips">${chips}${m ? mediaChip(m) : ''}${fo ? fontChip(fo) : ''}</div>`;
    }
    else body = '';
    const sub = [d.review?.data?.source?.kind, d.status === 'repaired' ? 'repaired' : null].filter(Boolean).join(' · ');
    return `<div class="card ${d.id === S.sel ? 'sel' : ''} ${d.status === 'error' ? 'err' : ''}" data-id="${d.id}" title="${esc(d.path)}">
      <button class="icon x" data-remove="${d.id}" aria-label="Remove from queue" title="Remove from queue (the file isn't touched)">✕</button>
      <div class="nm">${esc(d.name)}</div>${sub ? `<div class="sub">${esc(sub)}</div>` : ''}${body}</div>`;
  }).join('') || `<div class="queue-empty">Nothing here yet. Drop decks or folders anywhere in this window, or press ${isMac ? '⌘O' : 'Ctrl+O'}. ` +
    'Each deck is checked as soon as it arrives; nothing is changed until you click Repair.</div>';
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
  $('deck-chips').innerHTML = data ? summaryChips(data) : '';
  const busy = deck.status === 'scanning' || deck.status === 'repairing' || deck.status === 'queued';
  $('busy').hidden = !busy;
  if (busy) renderBusyOnly(deck);
  $('btn-repair').disabled = busy || deck.status === 'error';
  $('btn-repair').textContent = deck.status === 'repaired' ? 'Repair again' : 'Repair';
  // One primary button per screen (2.7): Repair until the deck is repaired, then the top alert's action.
  $('btn-repair').classList.toggle('p', deck.status !== 'repaired');
  // First-run hints (2.8). Export stays clickable when it can't run so it can say why (a disabled button
  // shows no tooltip); it only looks disabled.
  const exportWhy = S.settings.quickRepair ? 'Quick repair makes no report. Turn Quick repair off in Settings, then repair again.'
    : deck.status !== 'repaired' ? 'The report is made when you repair the deck. Repair first, then export it.' : '';
  $('btn-export').classList.toggle('off', !!exportWhy);
  $('btn-export').dataset.why = exportWhy;
  $('btn-export').title = exportWhy || 'Save the HTML report (before/after pictures and every finding) to share';
  const outName = `${deck.name}${S.settings.suffix || ' - mended'}.pptx`;
  $('btn-repair').title = `Writes "${outName}" ${S.settings.outputFolder ? `in ${S.settings.outputFolder}` : 'next to the original'}. ` +
    'Your original file is never changed.';
  $('btn-finder').textContent = isMac ? 'Show in Finder' : 'Show in Explorer';

  renderSource(deck);
  $('actions').innerHTML = deck.status === 'error' ? '' : actionBanners(deck);

  $('saved').hidden = !(deck.status === 'repaired' && deck.output);
  if (deck.output) {
    const name = deck.output.split(/[\\/]/).pop();
    $('saved').innerHTML = `Saved <b title="${esc(deck.output)}">${esc(name)}</b> · <a data-open-output>${isMac ? 'Show in Finder' : 'Show in Explorer'}</a> · <a data-open-mended>Open</a>`;
  }

  if (deck.status === 'error') {
    $('tab-review').innerHTML = `<div class="alert">✕ ${esc(deck.error)}</div>`;
    ['findings', 'media', 'fonts', 'options'].forEach((t) => { $(`tab-${t}`).innerHTML = ''; });
  } else {
    renderReview(deck);
    renderFindings(deck);
    renderMedia(deck);
    renderFonts(deck);
    renderOptions(deck);
  }
  document.querySelectorAll('#tabs button').forEach((b) => b.classList.toggle('on', b.dataset.tab === S.tab));
  ['review', 'findings', 'media', 'fonts', 'options'].forEach((t) => { $(`tab-${t}`).hidden = t !== S.tab; });
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

// ▶ VIDEO / ♪ AUDIO badge on every clip (David 2026-10-11): where media plays, at a glance.
function mediaHtml(media) {
  return (media || []).map((m) => `<div class="media-badge${m.kind === 'audio' ? ' audio' : ''}" style="left:${m.left.toFixed(2)}%;top:${m.top.toFixed(2)}%;width:${m.width.toFixed(2)}%;height:${m.height.toFixed(2)}%" title="${esc(`${m.kind === 'audio' ? 'Audio' : 'Video'}: ${m.start}${m.linked ? ' · linked, not embedded' : ''}`)}">` +
    `<span>${m.kind === 'audio' ? '♪ AUDIO' : '▶ VIDEO'}${m.start ? ` · ${esc(m.start)}` : ''}</span></div>`).join('');
}

function frameHtml(deck, caption, name, boxes, slide, media) {
  const url = imgUrl(deck, name);
  const inner = url ? `<img src="${url}" alt="${esc(caption)} slide ${slide}" draggable="false">` : '<div class="none">Not drawn (hidden slide)</div>';
  return `<div><span class="cap">${esc(caption)}</span><div class="frame" data-fs="${slide}">${inner}${mediaHtml(media)}${boxesHtml(boxes)}</div></div>`;
}

function renderReview(deck) {
  const data = deck.review?.data;
  const el = $('tab-review');
  if (!data) { el.innerHTML = '<p class="note">The review appears once the deck has been checked.</p>'; return; }
  const visuals = data.visuals || [];
  if (data.visuals_pending) {
    el.innerHTML = '<p class="note pending">Drawing the slides as PowerPoint shows them… The findings are ready in the Findings tab.</p>';
    return;
  }
  if (!visuals.length) {
    el.innerHTML = `<p class="note">${esc(data.visual_note || (deck.status === 'repaired' ? 'No slide changed visually.' : 'Nothing to show on the slides. See Findings.'))}</p>`;
    return;
  }
  const repaired = !!data.output;
  const legend = `<div class="legend">${Object.entries(KIND_LABEL).map(([k, l]) => `<span><i class="sw" style="border-color:var(--k-${k})"></i>${l}</span>`).join('')}` +
                 '<span>━ changed · ┅ needs a look · ✕ broken</span><span>Hover a box for details · double-click a slide for full screen</span></div>';
  const tiers = { 1: 'Broken: fix before the show', 2: 'Changes SlideTistic made: glance if you have time', 3: 'Needs a look' };
  let html = brokenStrip(deck) + legend;
  if (repaired && tuningOn() && voteStats(deck).votable.length) {
    html = `<div class="tuning-bar"><b>Tuning mode</b><span>${esc(tuningLine(deck))}</span><span class="grow"></span>` +
           `<button class="btn p" id="btn-vote">Start voting <kbd>V</kbd></button></div>` + html;
  }
  for (const t of [1, 2, 3]) {
    const block = visuals.filter((v) => v.tier === t && inFilter(v));
    if (!block.length) continue;
    const done = t === 1 ? ` · ${block.filter((v) => isChecked(deck, v)).length} checked` : '';
    html += `<h3 class="tier t${t}">${t}. ${tiers[t]} <small>· ${block.length} slide${block.length > 1 ? 's' : ''}${done}</small></h3>`;
    for (const v of block) html += v.deck ? deckCard(deck, v) : slideCard(deck, v, repaired);
  }
  if (S.reviewFilter !== 'all') {
    const hidden = visuals.filter((v) => v.tier !== 4 && !inFilter(v)).length;
    if (hidden) html += `<p class="fold">${hidden} more slide${hidden > 1 ? 's' : ''} hidden by the filter. <a data-rfilter="all">Show everything</a></p>`;
  } else {
    const same = visuals.filter((v) => v.tier === 4).map((v) => v.slide);
    if (same.length) html += `<p class="fold">4. Changed underneath, looks identical: slide${same.length > 1 ? 's' : ''} ${ranges(same)}.</p>`;
    const notes = visuals.filter((v) => v.tier === 5);
    if (notes.length) {
      html += `<details class="notes"${S.notesOpen ? ' open' : ''}><summary>5. Notes: low priority <small>· ${notes.length} slide${notes.length > 1 ? 's' : ''} ` +
              '(small text near an edge, a sliver of text over a picture)</small></summary>' +
              (S.notesOpen ? notes.map((v) => slideCard(deck, v, repaired)).join('') : '') + '</details>';
    }
  }
  el.innerHTML = html;
}

function deckCard(deck, v) {
  const list = v.reds.map((f) => `<li><b>${esc(f.check_id)}</b> ${esc(f.message)}</li>`).join('');
  return `<section class="slide sev-1${isChecked(deck, v) ? ' checked' : ''}" id="slide-deck"><div class="slide-head"><span class="sev r">✕ Broken</span>` +
         `<b>Whole deck</b>${checkedButton(deck, v, false)}</div><ul class="deck-reds">${list}</ul></section>`;
}

function slideCard(deck, v, repaired) {
  const canUndo = repaired && deck.review.data.prefit && !v.undone && (v.after_boxes || []).some((b) => b.mode === 'changed');
  const pair = repaired
    ? `<div class="pair">${frameHtml(deck, 'Before', v.before_png, v.before_boxes, v.slide, v.media)}${frameHtml(deck, v.undone ? 'After (layout changes undone)' : 'After', v.after_png, v.after_boxes, v.slide, v.media)}</div>`
    : `<div class="single">${frameHtml(deck, 'As PowerPoint draws it', v.before_png, v.before_boxes, v.slide, v.media)}</div>`;
  const badge = tierBadge(v);
  return `<section class="slide sev-${v.tier} ${v.undone ? 'undone' : ''}${isChecked(deck, v) ? ' checked' : ''}" id="slide-${v.slide}"><div class="slide-head">${badge}<b>Slide ${v.slide}</b>
    ${checkedButton(deck, v, false)}
    <button class="btn" data-fs="${v.slide}" title="Full screen (F)">⤢ Full screen</button>
    ${canUndo ? `<button class="btn" data-undo="${v.slide}" title="Put this slide back the way it was before layout fixes; font fixes stay">↶ Undo slide</button>` : ''}
    <button class="btn" data-ppt="${v.slide}" title="Open in PowerPoint at this slide">PowerPoint ↗</button>${votable(deck, v) ? voteControls(deck, v, false) : ''}</div>${pair}</section>`;
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
  const note = (f) => f.status === 'yellow' && !!f.evidence?.note;
  const rows = (data.findings || []).filter((f) => !f.informational && (S.filter === 'all'
    || (S.filter === 'note' ? note(f) : f.status === S.filter && !(S.filter === 'yellow' && note(f)))))
    .sort((a, b) => (ORDER[a.status] ?? 9) - (ORDER[b.status] ?? 9) || (a.slide || 0) - (b.slide || 0));
  const hasSlide = new Set((data.visuals || []).map((v) => v.slide));
  const filters = [['all', 'All'], ['red', '✕ Broken'], ['yellow', '! Look at'], ['note', '· Notes'], ['green_fixed', '✓ Fixed']]
    .map(([k, l]) => `<button data-filter="${k}" class="${S.filter === k ? 'on' : ''}">${l}</button>`).join('');
  const body = rows.map((f) => {
    const [icon, cls, word] = note(f) ? ['·', 'n', 'Note'] : ICON[f.status] || ['·', '', f.status];
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
    inv.map((r) => `<tr data-row-slide="${r.slide}">${cols.map(([, k]) => `<td>${esc(r[k])}</td>`).join('')}</tr>`).join('')}</tbody></table></div><p class="note">${esc(data.totals)}</p>`
    : '<p class="note">No video or audio in this deck.</p>';
  html += '<h3 class="section-title">To download <span class="note">fetch these and embed them before the show</span></h3>';
  html += dls.length ? `<div class="wrap"><table><thead><tr><th>Slide</th><th>Slide name</th><th>Site</th><th>Found in</th><th>Link</th></tr></thead><tbody>${
    dls.map((r) => `<tr data-row-slide="${r.slide}"><td>${r.slide}</td><td>${esc(r.slide_name)}</td><td>${esc(r.site)}</td><td>${esc(r.found_in)}</td><td><a data-url="${esc(r.url)}" style="color:var(--accent);cursor:pointer">${esc(r.url)}</a></td></tr>`).join('')}</tbody></table></div>`
    : '<p class="note">No video or media links found.</p>';
  el.innerHTML = html;
  if (S.mediaSlide) {
    const rows = el.querySelectorAll(`tr[data-row-slide="${S.mediaSlide}"]`);
    rows.forEach((r) => r.classList.add('hl'));
    requestAnimationFrame(() => rows[0]?.scrollIntoView({ behavior: 'smooth', block: 'center' }));
    S.mediaSlide = null;
  }
}

const FONT_LEVEL = { r: ['✕', 'r'], y: ['!', 'y'], n: ['·', 'n'], ok: ['✓', 'g'] };

function renderFonts(deck) {
  const data = deck.review?.data;
  const el = $('tab-fonts');
  if (!data) { el.innerHTML = ''; return; }
  const rows = data.fonts || [];
  if (!rows.length) { el.innerHTML = '<p class="note">No fonts named in this deck.</p>'; return; }
  const free = rows.filter((r) => r.free && r.level !== 'n');
  const busy = deck.fontsBusy || [];
  const label = (v) => `${({ 100: 'Thin', 200: 'ExtraLight', 300: 'Light', 400: 'Regular', 500: 'Medium', 600: 'SemiBold', 700: 'Bold', 800: 'ExtraBold', 900: 'Black' })[v[0]] || v[0]}${v[1] === 'italic' ? ' Italic' : ''}`;
  const ask = deck.fontsAsk;
  const action = (r) => {
    // Commercial fonts: Creative Cloud can't be driven from here, but its search is one click away.
    if (!r.free && r.level === 'r' && !r.here) {
      return `<a class="ext" data-url="https://fonts.adobe.com/search?query=${encodeURIComponent(r.family)}" title="Opens Adobe Fonts in your browser; activate it there with Creative Cloud">Search Adobe Fonts ↗</a>`;
    }
    if (!r.free || r.level === 'n') return '';
    if (busy.includes(r.family)) return '<span class="note pending">Installing…</span>';
    if (ask && ask.length === 1 && ask[0] === r.family) {
      return `<span class="confirm">Install ${esc(r.free.variants.map(label).join(', '))} for this user? <button class="btn p" data-fonts-yes>Install</button><button class="btn" data-fonts-no>Cancel</button></span>`;
    }
    const from = r.free.publisher ? `Free download from ${r.free.publisher}: ${r.free.license || ''}` : 'Free font (open licence) from Google Fonts / Fontsource';
    return `<button class="btn" data-font-get="${esc(r.family)}" title="${esc(from)}">Get ${esc(r.free.variants.map(label).join(', '))}</button>`;
  };
  const allAsk = ask && ask.length > 1;
  const collecting = deck.fontsCollecting;
  let html = '<div class="row" style="justify-content:space-between;align-items:center">' +
    '<p class="note" style="margin:0">Fonts PowerPoint needs on the show machine. Embedded and Office fonts travel with the deck; the rest must be installed there.</p>' +
    `<button class="btn" data-fonts-collect ${collecting ? 'disabled' : ''} title="Gather this deck's fonts in a folder next to it, named by what they are: copies of installed and Creative Cloud fonts, free ones downloaded. Opens the folder.">${collecting ? 'Collecting…' : 'Collect fonts next to deck'}</button>` +
    (free.length ? (allAsk
      ? `<span class="confirm">Install ${free.length} free font${free.length > 1 ? 's' : ''} (${esc(free.map((r) => r.family).join(', '))}) for this user? <button class="btn p" data-fonts-yes>Install</button><button class="btn" data-fonts-no>Cancel</button></span>`
      : `<button class="btn p" data-fonts-get-all ${busy.length ? 'disabled' : ''}>${busy.length ? 'Installing…' : `Get all ${free.length} free font${free.length > 1 ? 's' : ''}`}</button>`) : '') + '</div>';
  html += `<div class="wrap"><table><thead><tr><th></th><th>Font</th><th>Status</th><th>Shown on slides</th><th>Embedded</th><th></th></tr></thead><tbody>${rows.map((r) => {
    const [icon, cls] = FONT_LEVEL[r.level];
    const slides = r.slides.length ? ranges(r.slides) : `<span class="note">${esc(r.where || 'none')}</span>`;
    const swap = r.swap ? `<div class="why">Suggested swap: ${esc(r.swap)}</div>` : '';
    const here = r.level === 'r' || r.level === 'y'
      ? (r.here === 'creative_cloud' ? '<div class="why">On this computer through Creative Cloud (the show machine needs it too)</div>'
        : r.here === 'installed' ? '<div class="why">Installed on this computer (the show machine needs it too)</div>' : '') : '';
    const lacking = r.free?.unavailable?.length ? `<div class="why">Not in this family: ${esc(r.free.unavailable.map(label).join(', '))} (PowerPoint fakes it)</div>` : '';
    return `<tr class="${r.level === 'n' ? 'faint' : ''}"><td class="s ${cls}">${icon}</td><td><b>${esc(r.family)}</b></td><td>${esc(r.status)}${here}${swap}${lacking}</td>` +
           `<td>${slides}</td><td>${r.embedded ? 'Yes' : ''}</td><td>${action(r)}</td></tr>`;
  }).join('')}</tbody></table></div>`;
  if (free.length) html += '<p class="note">Free fonts come from their makers (Microsoft for Aptos), Fontsource or Google Fonts, and are installed for you only, no admin rights. PowerPoint must be restarted to see them, and the show machine needs them too (or embed them in PowerPoint).</p>';
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

const tierBadge = (v) => ({ 1: '<span class="sev r">✕ Broken</span>', 2: '<span class="sev c">Changed</span>', 3: '<span class="sev y">! Look at</span>',
                            5: '<span class="sev n">Note</span>' }[v.tier] || '');

// What's on this slide, in words (2.3): the viewer used to show it only on hover.
function viewerFindings(deck, v) {
  const icon = { red: '✕', tool_error: '?', yellow: '!', green_fixed: '✓' };
  const rows = (deck.review.data.findings || []).filter((f) => f.slide === v.slide && !f.informational && icon[f.status]);
  if (!rows.length) return '';
  const order = { red: 0, tool_error: 0, yellow: 1, green_fixed: 2 };
  rows.sort((a, b) => order[a.status] - order[b.status]);
  return rows.map((f) => {
    const cls = { red: 'r', tool_error: 'r', yellow: 'y', green_fixed: 'g' }[f.status];
    const why = S.settings.showWhy && f.evidence?.rule ? `<small>Why: ${esc(f.evidence.rule)}</small>` : '';
    return `<li class="${cls}"><span class="fi">${icon[f.status]}</span><span><b>${esc(f.check_id)}</b> ${esc(f.message)}${why}</span></li>`;
  }).join('');
}

function renderViewer() {
  const deck = selected();
  const visuals = deck?.review?.data?.visuals || [];
  const v = visuals[S.viewer.idx];
  if (!v) { closeViewer(); return; }
  const repaired = !!deck.review.data.output;
  const shown = visuals.filter(inFilter);       // the counter follows the review filter (R)
  const pos = shown.indexOf(v);
  $('viewer-title').innerHTML = `${tierBadge(v)} Slide ${v.slide}  ·  ${pos >= 0 ? pos + 1 : '–'} of ${shown.length}` +
    (S.reviewFilter !== 'all' ? ' <small class="dim">(filtered: R shows all)</small>' : '');
  const list = viewerFindings(deck, v);
  $('viewer-findings').hidden = !list;
  $('viewer-findings').innerHTML = list ? `<ul>${list}</ul>` : '';
  const canUndo = repaired && deck.review.data.prefit && !v.undone && (v.after_boxes || []).some((b) => b.mode === 'changed');
  $('v-undo').hidden = !canUndo;
  $('v-mode').hidden = !repaired;
  let html;
  if (!repaired) {
    html = `<div class="pane">${frameHtml(deck, 'As PowerPoint draws it', v.before_png, v.before_boxes, v.slide, v.media)}</div>`;
    $('viewer-mode').textContent = '';
  } else if (S.viewer.mode === 'side') {
    html = `<div class="pane">${frameHtml(deck, 'Before', v.before_png, v.before_boxes, v.slide, v.media)}</div>` +
           `<div class="pane">${frameHtml(deck, v.undone ? 'After (undone)' : 'After', v.after_png, v.after_boxes, v.slide, v.media)}</div>`;
    $('viewer-mode').textContent = 'side by side';
  } else {
    const before = S.viewer.flipShow === 'before';
    html = `<div class="pane" style="max-width:1400px">${frameHtml(deck, before ? 'BEFORE' : 'AFTER', before ? v.before_png : v.after_png,
            before ? v.before_boxes : v.after_boxes, v.slide, v.media)}</div>`;
    $('viewer-mode').textContent = `flip view · showing ${before ? 'BEFORE' : 'AFTER'} (hold Space or press B)`;
  }
  $('viewer-stage').innerHTML = html;
  $('v-checked').innerHTML = checkedButton(deck, v, true);
  const voting = votable(deck, v);
  $('v-vote').hidden = !voting;
  if (voting) $('v-vote').innerHTML = `${voteControls(deck, v, true)}<span class="note">${esc(tuningLine(deck))}</span>`;
  $('viewer-hint').innerHTML = voting
    ? '← → slides · <kbd>Y</kbd>/<kbd>↑</kbd> 👍 next · <kbd>N</kbd>/<kbd>↓</kbd> 👎 · <kbd>1</kbd>–<kbd>4</kbd> 👎 with why, next · <kbd>0</kbd> clear · <kbd>B</kbd>/<kbd>Space</kbd> flip · <kbd>U</kbd> undo · <kbd>Esc</kbd> close'
    : '← → slides · <kbd>B</kbd> / hold <kbd>Space</kbd> flip before↔after · <kbd>C</kbd> mark checked · <kbd>R</kbd> broken only · <kbd>U</kbd> undo this slide · <kbd>P</kbd> open in PowerPoint · <kbd>Esc</kbd> close';
}

function setReviewFilter(f) {
  S.reviewFilter = f;
  if (S.viewer) {
    const v = (selected()?.review?.data?.visuals || [])[S.viewer.idx];
    if (v && !inFilter(v)) viewerStep(1); else renderViewer();
  }
  const d = selected();
  if (d) renderReview(d);
  if (f === 'broken') toast('Showing broken slides only. R shows everything again.');
}

function closeViewer() { S.viewer = null; $('viewer').hidden = true; }
function viewerStep(d) {
  const visuals = selected()?.review?.data?.visuals || [];
  const n = visuals.length;
  if (!n) return;
  // Follow the review filter, so a rushed operator steps through only the broken slides.
  for (let k = 1; k <= n; k++) {
    const i = ((S.viewer.idx + d * k) % n + n) % n;
    if (S.reviewFilter === 'all' || inFilter(visuals[i])) { S.viewer.idx = i; break; }
  }
  renderViewer();
}
const viewerSlide = () => (selected()?.review?.data?.visuals || [])[S.viewer?.idx]?.slide;

// ---------------------------------------------------------------------------------------------
// Actions

// Keys that throw work away take two presses (2.4; VEP: two-step confirm, no undo toast). The first press says
// what the second will do; the second must come within 3 seconds.
let armedKey = null;
function confirmKey(id, message) {
  if (armedKey && armedKey.id === id && Date.now() - armedKey.t < 3000) { armedKey = null; return true; }
  armedKey = { id, t: Date.now() };
  toast(message);
  return false;
}

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

const fmtMB = (b) => (b >= 1e9 ? `${(b / 1e9).toFixed(1)} GB` : `${Math.round(b / 1e6)} MB`);
function showTempSize(r) {
  $('d-temp').textContent = `Temporary files: ${fmtMB(r.bytes)}. Slide pictures and undo copies for the decks in the queue are kept.`;
}

async function openSettings() {
  const s = S.settings;
  $('s-output').value = s.outputFolder || ''; $('s-suffix').value = s.suffix; $('s-safe').value = s.safeZonePct;
  $('s-quick').checked = !!s.quickRepair; $('s-watch').value = s.watchFolder || ''; $('s-crew').value = s.crewFonts || '';
  $('s-why').checked = !!s.showWhy;
  $('s-shapecache').checked = s.shapeCache !== false;
  $('s-partial').value = s.partialExport || 'off';
  $('s-hideppt').checked = s.hidePowerPoint !== false;
  $('s-tuning').checked = !!s.tuningMode;
  document.querySelectorAll('.mac-only').forEach((el) => { el.hidden = !isMac; });
  document.querySelectorAll('.skin').forEach((b) => b.classList.toggle('on', b.dataset.skin === s.skin));
  $('diag').innerHTML = `SlideTistic ${esc(S.info.version)} · ${esc(S.info.platform)} · PowerPoint ${S.info.powerpoint === null ? 'n/a' : S.info.powerpoint ? 'found' : 'not found (no visual review or layout fixes)'}<br>` +
    `${S.checks.length} checks: ${S.checks.map((c) => `${c.id} v${c.version}`).join(', ')}<br>Log: ${esc(S.info.logFile)}`;
  $('d-log').textContent = await api.logTail(120);
  $('settings').hidden = false;
  showTempSize(await api.tempSize());
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
  // The top banner tells the operator at once (David 2026-10-12: he only found the update in Diagnostics).
  const banner = (text, { restart = false, move = false, pct = null } = {}) => {
    $('update-text').textContent = text;
    $('update-restart').hidden = !restart;
    $('update-move').hidden = !move;
    $('update-bar').hidden = pct === null;
    if (pct !== null) $('update-bar').firstElementChild.style.width = `${pct}%`;
    if (!S.updateDismissed) $('update-banner').hidden = false;
  };
  if (st.type === 'checking') { line.textContent = 'Checking GitHub Releases…'; bar.hidden = true; }
  else if (st.type === 'not-available') { line.textContent = 'You have the latest version.'; bar.hidden = true; }
  else if (st.type === 'available') {
    line.textContent = `Update available: v${st.version}, downloading…`; fill(0); S.updateVersion = st.version;
    if (S.moveNeeded) banner(`SlideTistic v${st.version} is out. Move SlideTistic to Applications first, so it can update itself.`, { move: true });
    else { banner(`Downloading SlideTistic v${st.version}…`, { pct: 0 }); api.downloadUpdate(); }
  } else if (st.type === 'progress') {
    const parts = [`${Math.round(st.percent)}%`, `${(st.transferred / 1048576).toFixed(1)} / ${(st.total / 1048576).toFixed(1)} MB`];
    if (st.bytesPerSecond > 0) parts.push(fmtSpeed(st.bytesPerSecond), fmtETA((st.total - st.transferred) / st.bytesPerSecond));
    line.textContent = parts.join('  ·  ');
    fill(st.percent);
    banner(`Downloading SlideTistic v${S.updateVersion || ''}…  ${parts.join('  ·  ')}`, { pct: st.percent });
  } else if (st.type === 'downloaded') {
    line.textContent = `v${st.version} ready: see the banner above.`;
    fill(100);
    banner(`SlideTistic v${st.version} is ready. Restart to finish updating.`, { restart: true });
  } else if (st.type === 'move-needed') {
    S.moveNeeded = true;
    const why = { translocated: 'it was opened straight from Downloads', 'disk image': 'it\'s running from the disk image' }[st.where] || 'it isn\'t in the Applications folder';
    line.textContent = `Updates can't install: ${why}. Move SlideTistic to Applications.`;
    banner(`SlideTistic can't update itself because ${why}. Move it to Applications (it reopens from there).`, { move: true });
  } else if (st.type === 'error') {
    line.textContent = `Update error: ${st.message}`; bar.hidden = true;
    // Show the raw message (global recipe): it usually says exactly what's wrong.
    banner(`Update error: ${st.message}`, { move: /read-only volume|move the application/i.test(st.message || '') });
  }
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
    if ($('btn-export').dataset.why) { toast($('btn-export').dataset.why); return; }
    const r = await api.exportReport(d.id, d.name);
    if (r.error) toast(r.error); else if (r.path) toast(`Report saved: ${r.path}`);
  };
  $('btn-settings').onclick = openSettings;
  $('btn-slidefluid').onclick = async () => {
    const r = await api.openSlideFluid();
    if (r.error) {        // not installed: take them to the download page (David 2026-10-12)
      toast("SlideFluid isn't installed on this computer. Opening its download page.");
      api.openExternal(SLIDEFLUID_RELEASES);
    }
  };
  $('vep').onclick = (e) => { e.preventDefault(); api.openExternal('https://veproductions.net'); };
  $('update-restart').onclick = () => api.installUpdate();
  $('d-temp-clear').onclick = async () => {
    const b = $('d-temp-clear');
    b.disabled = true; b.textContent = 'Clearing…';
    showTempSize(await api.clearTemp(S.decks.map((d) => d.id)));
    b.disabled = false; b.textContent = 'Clear temporary files';
  };
  $('update-dismiss').onclick = () => { $('update-banner').hidden = true; S.updateDismissed = true; };
  $('update-move').onclick = async () => {
    $('update-move').disabled = true; $('update-move').textContent = 'Moving…';
    const r = await api.moveToApplications();
    if (r?.error) { toast(`Couldn't move it: ${r.error}. Drag SlideTistic into Applications in Finder, then open it from there.`); }
    $('update-move').disabled = false; $('update-move').textContent = 'Move to Applications';
  };
  $('d-update').onclick = () => api.checkForUpdate?.().catch?.(() => { $('d-update-status').textContent = 'Updates work in the installed app, not in development.'; });

  $('tabs').onclick = (e) => { const t = e.target.closest('button')?.dataset.tab; if (t) setTab(t); };

  document.addEventListener('click', (e) => {
    const t = e.target;
    const card = t.closest('.card');
    if (t.closest('[data-remove]')) { const d = S.decks.find((x) => x.id === t.closest('[data-remove]').dataset.remove); if (d) removeDeck(d); return; }
    if (card) { S.sel = card.dataset.id; render(); return; }
    const fs = t.closest('button[data-fs]'); if (fs) { openViewer(Number(fs.dataset.fs)); return; }
    const vb = t.closest('[data-vote], [data-reason]');
    if (vb) {
      const d = selected();
      const v = (d?.review?.data?.visuals || []).find((x) => x.slide === Number(vb.dataset.vslide));
      if (!v || !votable(d, v)) return;
      const cur = voteOf(d, v);
      if (vb.dataset.reason) castVote(d, v, 'down', cur?.reason === vb.dataset.reason ? null : vb.dataset.reason);
      else castVote(d, v, cur?.vote === vb.dataset.vote && !cur?.reason ? 'clear' : vb.dataset.vote, null);
      return;
    }
    if (t.closest('#btn-vote')) { startVoting(); return; }
    const ck = t.closest('[data-checked]');
    if (ck) {
      const d = selected();
      const v = ck.dataset.checked === 'deck' ? deckItem(d) : (d?.review?.data?.visuals || []).find((x) => x.slide === Number(ck.dataset.checked));
      if (v) toggleChecked(d, v);
      return;
    }
    const rf = t.closest('[data-rfilter]'); if (rf) { setReviewFilter(rf.dataset.rfilter); return; }
    const nt = t.closest('details.notes > summary');
    if (nt) { e.preventDefault(); S.notesOpen = !S.notesOpen; renderReview(selected()); return; }
    const un = t.closest('[data-undo]'); if (un) { undoSlide(Number(un.dataset.undo)); return; }
    const pp = t.closest('[data-ppt]'); if (pp) { openInPowerPoint(Number(pp.dataset.ppt)); return; }
    const jp = t.closest('[data-jump]'); if (jp) { jumpToSlide(Number(jp.dataset.jump)); return; }
    const ab = t.closest('#actions [data-act]'); if (ab) { bannerAction(selected(), ab); return; }
    const sl = t.closest('#actions [data-slide]'); if (sl) { jumpToSlide(Number(sl.dataset.slide)); return; }
    if (t.closest('[data-goto-media]')) { setTab('media'); return; }
    if (t.closest('[data-goto-fonts]')) { setTab('fonts'); return; }
    const fsl = t.closest('[data-fslide]'); if (fsl) { jumpToSlide(Number(fsl.dataset.fslide)); return; }
    const fg = t.closest('[data-font-get]'); if (fg) { const d = selected(); d.fontsAsk = [fg.dataset.fontGet]; renderFonts(d); return; }
    if (t.closest('[data-fonts-get-all]')) {
      const d = selected();
      d.fontsAsk = (d.review.data.fonts || []).filter((r) => r.free && r.level !== 'n').map((r) => r.family);
      if (S.tab !== 'fonts') setTab('fonts'); else renderFonts(d);
      return;
    }
    if (t.closest('[data-fonts-collect]')) { collectFonts(selected()); return; }
    if (t.closest('[data-fonts-yes]')) { const d = selected(); const fams = d.fontsAsk || []; d.fontsAsk = null; getFonts(d, fams); return; }
    if (t.closest('[data-fonts-no]')) { const d = selected(); d.fontsAsk = null; renderFonts(d); return; }
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
    if (t.id === 's-shapecache') setSetting('shapeCache', t.checked);
    if (t.id === 's-partial') setSetting('partialExport', t.value);
    if (t.id === 's-hideppt') setSetting('hidePowerPoint', t.checked);
    if (t.id === 's-tuning') {
      setSetting('tuningMode', t.checked).then(async () => {
        for (const d of S.decks) if (d.review) await loadVotes(d);
        render();
        if (t.checked) toast(S.voteTotals ? `Tuning mode on. Votes are saved in ${S.voteTotals.dir}` : 'Tuning mode on.');
      });
    }
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
    else if (e.key.toLowerCase() === 'u' && !$('v-undo').hidden) {
      const n = viewerSlide();
      if (confirmKey(`u${n}`, `Press U again to put slide ${n} back the way it was before the layout fixes.`)) undoSlide(n);
    }
    else if (e.key.toLowerCase() === 'p') openInPowerPoint(viewerSlide());
    else if (e.key.toLowerCase() === 'c' && !mod) { const d = selected(); const v = d?.review?.data?.visuals?.[S.viewer.idx]; if (v) toggleChecked(d, v); }
    else if (e.key.toLowerCase() === 'r' && !mod) setReviewFilter(S.reviewFilter === 'broken' ? 'all' : 'broken');
    else if (!$('v-vote').hidden) {
      const k = e.key.toLowerCase();
      if (k === 'y' || e.key === 'ArrowUp') { e.preventDefault(); voteInViewer('up', null, true); }
      else if (k === 'n' || e.key === 'ArrowDown') { e.preventDefault(); voteInViewer('down'); }
      else if (['1', '2', '3', '4'].includes(e.key)) voteInViewer('down', REASONS[Number(e.key) - 1][0], true);
      else if (e.key === '0') voteInViewer('clear');
    }
    return;
  }
  if (e.key === 'Escape') { document.querySelectorAll('.modal-back').forEach((m) => { m.hidden = true; }); return; }
  if (typing || [...document.querySelectorAll('.modal-back')].some((m) => !m.hidden)) return;   // not behind a dialog
  if (mod && e.key.toLowerCase() === 'o') { e.preventDefault(); $('btn-add').click(); }
  else if (mod && e.shiftKey && e.key.toLowerCase() === 'r') { e.preventDefault(); repairAll(); }
  else if (mod && e.key.toLowerCase() === 'r') { e.preventDefault(); repair(selected()); }
  else if (mod && e.key.toLowerCase() === 'e') { e.preventDefault(); $('btn-export').click(); }
  else if (mod && e.key === ',') { e.preventDefault(); openSettings(); }
  else if (e.key === '?') $('shortcuts').hidden = false;
  else if (e.key.toLowerCase() === 'v' && !mod && tuningOn()) startVoting();
  else if (e.key.toLowerCase() === 'r' && !mod && selected()?.review) { setTab('review'); setReviewFilter(S.reviewFilter === 'broken' ? 'all' : 'broken'); }
  else if (mod && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {      // plain arrows scroll the review (2.5)
    if (!S.decks.length) return;
    e.preventDefault();
    const i = S.decks.findIndex((d) => d.id === S.sel);
    const j = Math.max(0, Math.min(S.decks.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)));
    S.sel = S.decks[j].id; render();
  } else if (e.key === 'Backspace' || e.key === 'Delete') {
    const d = selected();
    if (d && confirmKey(`rm${d.id}`, `Press ${e.key === 'Delete' ? 'Delete' : 'Backspace'} again to remove "${d.name}" from the queue${
      d.status === 'scanning' || d.status === 'repairing' ? ' (stops its job)' : ''}.`)) removeDeck(d);
  }
  else if (['1', '2', '3', '4', '5'].includes(e.key)) setTab(['review', 'findings', 'media', 'fonts', 'options'][Number(e.key) - 1]);
  else if (e.key.toLowerCase() === 'f') {
    const v = (selected()?.review?.data?.visuals || []).find((x) => x.tier < 4) || (selected()?.review?.data?.visuals || [])[0];
    if (v) openViewer(v.slide);
  }
}

init();
