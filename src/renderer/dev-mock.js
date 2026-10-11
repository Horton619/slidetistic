/* Preview mode: only when this page is opened in an ordinary browser (no Electron preload), stand in
   for the engine using a saved review bundle so the screens can be checked without the app.
   Inert inside SlideTistic itself. */
(function () {
  if (window.slidetistic || !location.protocol.startsWith('http')) return;
  const ROOT = '/corpus/reviews';
  const BUNDLE = new URLSearchParams(location.search).get('review') || 'pat';   // a folder under corpus/reviews
  let settings = { outputFolder: '', suffix: ' - mended', safeZonePct: 5, quickRepair: false, crewFonts: '',
    skin: new URLSearchParams(location.search).get('skin') || 'pro', showWhy: true, watchFolder: '', presets: {}, lastTab: 'review' };
  const listeners = [];
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
