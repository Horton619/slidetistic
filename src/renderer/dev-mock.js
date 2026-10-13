/* Preview mode: only when this page is opened in an ordinary browser (no Electron preload), stand in
   for the engine using a saved review bundle so the screens can be checked without the app.
   Inert inside SlideTistic itself. */
(function () {
  if (window.slidetistic || !location.protocol.startsWith('http')) return;
  const ROOT = '/corpus/reviews';
  const BUNDLE = new URLSearchParams(location.search).get('review') || 'pat';   // a folder under corpus/reviews
  let settings = { outputFolder: '', suffix: ' - mended', safeZonePct: 5, quickRepair: false, crewFonts: '',
    skin: new URLSearchParams(location.search).get('skin') || 'pro', showWhy: true, watchFolder: '', presets: {}, lastTab: 'review',
    tuningMode: new URLSearchParams(location.search).has('tuning') };
  const listeners = [];
  const activation = [];
  const votes = [];
  const checked = {};
  const emit = (ev) => listeners.forEach((cb) => cb(ev));
  const later = (ms, fn) => new Promise((r) => setTimeout(() => { fn(); r(); }, ms));
  async function run(deckId, kind) {
    const stages = kind === 'repair'
      ? [{ stage: 'fix', check: 'F001', index: 1, total: 7 }, { stage: 'fit', round: 1, rounds: 6 }, { stage: 'fit', round: 2, rounds: 6 }, { stage: 'safety' }, { stage: 'render' }]
      : [{ stage: 'scan', check: 'F001', index: 3, total: 40 }, { stage: 'scan', check: 'M002', index: 30, total: 40 }];
    for (const s of stages) await later(500, () => emit({ deckId, kind, type: 'progress', ...s }));
    await later(400, () => emit({ deckId, kind, type: 'done', code: 0 }));
  }
  window.slidetistic = {
    getSettings: async () => settings,
    setSetting: async (k, v) => { settings = { ...settings, [k]: v }; return settings; },
    pathForFile: (f) => f.name, pickFiles: async () => ['/Users/demo/Downloads/03 - PAT MBD Presentation.pptx'], pickFolder: async () => '/Users/demo/Shows',
    expand: async (paths) => paths.map((p) => ({ path: p, name: p.split('/').pop(), size: 22000000, isDir: false, ext: '.' + p.split('.').pop().toLowerCase() })),
    listChecks: async () => (await fetch(`${ROOT}/checks.json`)).json(),
    scan: async (id) => { run(id, 'scan'); return {}; },
    repair: async (id) => { run(id, 'repair'); return { output: '/Users/demo/Downloads/03 - PAT MBD Presentation - mended.pptx' }; },
    undoSlide: async (id, _m, slide) => { setTimeout(() => emit({ deckId: id, kind: 'undo', type: 'undone', slide }), 600); return {}; },
    cancel: async () => {},
    adobeFonts: async (fams) => { await new Promise((r) => setTimeout(r, 700)); return Object.fromEntries(fams.map((f) => [f, { info: /museo|gotham|proxima/i.test(f) ? { name: f, link: `https://fonts.adobe.com/fonts/${f.toLowerCase().replace(/\W+/g, '-')}` } : null }])); },
    activateFonts: async (deckId, items) => { const fams = items.map((i) => i.family); setTimeout(() => activation.forEach((cb) => cb({ deckId, finished: true, done: fams.slice(0, 1), total: fams.length })), 2500); activation.forEach((cb) => cb({ deckId, current: fams[0], index: 0, total: fams.length, done: [] })); return { ok: true }; },
    onFontActivation: (cb) => { activation.push(cb); return () => {}; },
    collectFonts: async () => { await new Promise((r) => setTimeout(r, 900)); return { folder: '/Users/demo/Shows/Deck - fonts', events: [{ type: 'font', name: 'Proxima Nova Bold', how: 'Creative Cloud (link)' }, { type: 'font', name: 'Museo Sans 500 Regular', how: 'not found' }] }; },
    getFonts: async (_f, fams) => { await new Promise((r) => setTimeout(r, 1200)); return { events: fams.map((f) => ({ type: 'font', family: f, ok: true, license: 'OFL-1.1', message: `${f} (OFL-1.1): 400 installed` })).concat([{ type: 'done', message: 'Restart PowerPoint to use the new fonts.' }]) }; },
    loadChecked: async (k) => ({ ...(checked[k] || {}) }),
    setChecked: async (k, slide, sig) => { checked[k] = { ...(checked[k] || {}) }; if (sig) checked[k][slide] = { sig }; else delete checked[k][slide]; return { ok: true }; },
    vote: async (r) => { votes.push({ ...r, t: new Date().toISOString() }); return { ok: true }; },
    loadVotes: async (sha) => ({ dir: '(preview)', total: votes.length, up: votes.filter((v) => v.vote === 'up').length, deck: votes.filter((v) => v.deck_sha12 === sha) }),
    discardReview: async () => {}, tempSize: async () => ({ bytes: 36e6 }), clearTemp: async () => ({ bytes: 2e6 }),
    loadReview: async () => ({ dir: `${location.origin}${ROOT}/${BUNDLE}`, data: await (await fetch(`${ROOT}/${BUNDLE}/review.json`)).json() }),
    onEngineEvent: (cb) => { listeners.push(cb); return () => {}; },
    exportReport: async () => ({ path: '/Users/demo/Downloads/report.html' }), exportMedia: async () => ({ path: '/Users/demo/Downloads/media.xlsx' }),
    showInFolder: async () => {}, openPath: async () => {}, openExternal: async () => {}, openAtSlide: async () => ({ ok: true }),
    info: async () => ({ version: 'preview', platform: 'darwin', powerpoint: true, logFile: '(preview)' }),
    openSlideFluid: async () => ({ ok: true }), logTail: async () => '(preview mode)', onWatchFound: () => () => {},
    checkForUpdate: async () => {}, downloadUpdate: async () => {}, installUpdate: () => {}, onUpdateStatus: () => () => {},
  };
})();
