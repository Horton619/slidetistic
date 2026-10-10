// SlideTistic — Electron main process.
// The engine is a Python CLI (`engine.cli`) run as a subprocess that prints one JSON object per line
// (SlideFluid's NDJSON pattern). Jobs run one at a time: PowerPoint can only render one deck at once.

const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const fs = require('fs');
const os = require('os');
const { spawn, execFile } = require('child_process');

const isMac = process.platform === 'darwin';
let mainWindow = null;

// ---------------------------------------------------------------------------------------------
// Logger (userData/slidetistic.log, rotates at 2 MB)

const logFile = () => path.join(app.getPath('userData'), 'slidetistic.log');
function log(level, ...parts) {
  try {
    const f = logFile();
    if (fs.existsSync(f) && fs.statSync(f).size > 2 * 1024 * 1024) fs.renameSync(f, f + '.1');
    fs.appendFileSync(f, `${new Date().toISOString()} [${level}] ${parts.join(' ')}\n`);
  } catch (_) { /* logging must never break the app */ }
}

// ---------------------------------------------------------------------------------------------
// Settings (userData/slidetistic-settings.json). Loose schema: defaults fill missing keys.

const DEFAULTS = {
  outputFolder: '',            // '' = next to the original (fallback: Downloads on Mac, Desktop on Windows)
  suffix: ' - mended',
  safeZonePct: 5,
  quickRepair: false,          // true = skip layout fixes + visual review
  crewFonts: '',               // one per line
  skin: 'pro',
  showWhy: true,               // diagnostic mode: the rule behind each call
  watchFolder: '',
  presets: {},                 // { canva: { F001: {check:true, fix:true}, … }, … }
  lastTab: 'review',
  window: { width: 1360, height: 860 },
};
const settingsFile = () => path.join(app.getPath('userData'), 'slidetistic-settings.json');
function loadSettings() {
  try { return { ...DEFAULTS, ...JSON.parse(fs.readFileSync(settingsFile(), 'utf8')) }; }
  catch (_) { return { ...DEFAULTS }; }
}
let settings = null;
function saveSettings() {
  fs.mkdirSync(path.dirname(settingsFile()), { recursive: true });
  fs.writeFileSync(settingsFile(), JSON.stringify(settings, null, 2));
}

// ---------------------------------------------------------------------------------------------
// Engine: dev = project venv `python -m engine.cli`; packaged = PyInstaller folder in resources.
// SLIDETISTIC_TOOLS points the engine at the bundled Poppler + ffprobe (falls back to PATH in dev).

function engineCommand(args) {
  const exeName = isMac ? 'slidetistic_engine' : 'slidetistic_engine.exe';
  if (app.isPackaged) {
    const res = process.resourcesPath;
    return { cmd: path.join(res, 'backend', 'slidetistic_engine', exeName), args, cwd: res,
             env: { ...process.env, SLIDETISTIC_TOOLS: path.join(res, 'tools') } };
  }
  const root = path.join(__dirname, '..');
  const py = path.join(root, 'venv', isMac ? 'bin/python' : 'Scripts/python.exe');
  return { cmd: py, args: ['-m', 'engine.cli', ...args], cwd: root,
           env: { ...process.env, SLIDETISTIC_TOOLS: path.join(root, 'vendor', isMac ? 'mac' : 'win') } };
}

// One job at a time; each job streams its events to the renderer as `engine:event`.
const jobs = [];
let running = null;

function enqueue(job) {
  jobs.push(job);
  send('engine:event', { jobId: job.id, deckId: job.deckId, type: 'queued', kind: job.kind });
  pump();
}

function pump() {
  if (running || !jobs.length) return;
  running = jobs.shift();
  const job = running;
  const { cmd, args, cwd, env } = engineCommand(job.args);
  log('info', 'engine', job.kind, args.join(' '));
  send('engine:event', { jobId: job.id, deckId: job.deckId, type: 'started', kind: job.kind });
  const child = spawn(cmd, args, { cwd, env });
  job.child = child;
  let buf = '';
  let stderr = '';
  child.stdout.on('data', (d) => {
    buf += d.toString();
    let i;
    while ((i = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, i).trim();
      buf = buf.slice(i + 1);
      if (!line.startsWith('{')) continue;
      try {
        const ev = JSON.parse(line);
        if (ev.type === 'error' || ev.type === 'warn') log(ev.type, job.kind, ev.message || '');
        send('engine:event', { jobId: job.id, deckId: job.deckId, kind: job.kind, ...ev });
      } catch (_) { /* partial or non-JSON line */ }
    }
  });
  child.stderr.on('data', (d) => { stderr += d.toString(); });
  child.on('close', (code) => {
    if (code && stderr) log('error', job.kind, stderr.slice(-2000));
    send('engine:event', {
      jobId: job.id, deckId: job.deckId, kind: job.kind, type: 'done', code,
      cancelled: !!job.cancelled, stderr: code ? stderr.slice(-800) : '',
    });
    running = null;
    pump();
  });
}

function send(channel, payload) {
  if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send(channel, payload);
}

let jobCounter = 0;
const reviewDir = (deckId) => path.join(app.getPath('userData'), 'reviews', deckId);

function commonArgs(opts) {
  const a = ['--json', '--set', `safe_zone_pct=${settings.safeZonePct}`];
  const crew = settings.crewFonts.split('\n').map((s) => s.trim()).filter(Boolean);
  if (crew.length) a.push('--crew-fonts', crew.join(','));
  if (opts.checks) a.push('--checks', opts.checks.join(','));
  if (opts.preset) a.push('--preset', opts.preset);
  return a;
}

function outputPathFor(input) {
  const base = path.basename(input, path.extname(input)) + settings.suffix;
  const candidates = [];
  if (settings.outputFolder) candidates.push(settings.outputFolder);
  candidates.push(path.dirname(input), isMac ? app.getPath('downloads') : app.getPath('desktop'));
  const folder = candidates.find((dir) => {
    try { fs.accessSync(dir, fs.constants.W_OK); return true; } catch (_) { return false; }
  });
  // Never overwrite: "Deck - mended.pptx", then "Deck - mended (2).pptx", …
  let out = path.join(folder, base + '.pptx');
  for (let n = 2; fs.existsSync(out); n++) out = path.join(folder, `${base} (${n}).pptx`);
  return out;
}

// ---------------------------------------------------------------------------------------------
// IPC

ipcMain.handle('settings:getAll', () => settings);
ipcMain.handle('settings:set', (_e, key, value) => {
  settings[key] = value;
  saveSettings();
  if (key === 'watchFolder') startWatching();
  return settings;
});

ipcMain.handle('dialog:openFiles', async () => {
  const r = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile', 'openDirectory', 'multiSelections'],
    filters: [{ name: 'Presentations', extensions: ['pptx', 'ppt', 'key', 'pptm'] }],
  });
  return r.canceled ? [] : r.filePaths;
});
ipcMain.handle('dialog:openFolder', async () => {
  const r = await dialog.showOpenDialog(mainWindow, { properties: ['openDirectory', 'createDirectory'] });
  return r.canceled ? null : r.filePaths[0];
});
ipcMain.handle('dialog:saveFile', async (_e, defaultPath, filters) => {
  const r = await dialog.showSaveDialog(mainWindow, { defaultPath, filters });
  return r.canceled ? null : r.filePath;
});

// Dropped/picked paths → decks. Folders are walked; a folder NAMED *.pptx (slide-image exports, seen in
// Dropbox) is reported as such rather than walked.
ipcMain.handle('files:expand', (_e, paths) => {
  const out = [];
  const visit = (p, depth) => {
    let st;
    try { st = fs.statSync(p); } catch (_) { return; }
    const ext = path.extname(p).toLowerCase();
    if (st.isDirectory() && !['.pptx', '.key'].includes(ext)) {
      if (depth > 6) return;
      for (const name of fs.readdirSync(p)) {
        if (!name.startsWith('.') && !name.startsWith('~$')) visit(path.join(p, name), depth + 1);
      }
      return;
    }
    if (['.pptx', '.ppt', '.key', '.pptm'].includes(ext) && !path.basename(p).includes(settings.suffix)) {
      out.push({ path: p, name: path.basename(p), size: st.isDirectory() ? 0 : st.size, isDir: st.isDirectory(), ext });
    }
  };
  for (const p of paths) visit(p, 0);
  return out;
});

ipcMain.handle('engine:listChecks', () => new Promise((resolve) => {
  const { cmd, args, cwd, env } = engineCommand(['list-checks', '--json']);
  execFile(cmd, args, { cwd, env, maxBuffer: 10 * 1024 * 1024 }, (err, stdout) => {
    if (err) { log('error', 'list-checks', err.message); resolve([]); return; }
    try { resolve(JSON.parse(stdout)); } catch (_) { resolve([]); }
  });
}));

ipcMain.handle('engine:scan', (_e, deckId, file, opts = {}) => {
  const dir = reviewDir(deckId);
  fs.rmSync(dir, { recursive: true, force: true });
  const id = `j${++jobCounter}`;
  // With PowerPoint (Mac), judge off-slide text by the words actually drawn (~4 s more per deck);
  // without it the engine falls back to box geometry on its own.
  const layout = settings.quickRepair ? '--no-layout' : '--layout';
  enqueue({ id, deckId, kind: 'scan', args: ['scan', file, ...commonArgs(opts), '--review-dir', dir, layout] });
  return { jobId: id, reviewDir: dir };
});

ipcMain.handle('engine:repair', (_e, deckId, file, opts = {}) => {
  const dir = reviewDir(deckId);
  fs.rmSync(dir, { recursive: true, force: true });
  const out = outputPathFor(file);
  const args = ['repair', file, ...commonArgs(opts), '--out', out, '--review-dir', dir];
  if (opts.fixes) args.push('--fix', opts.fixes.join(','));
  if (settings.quickRepair) args.push('--no-layout', '--no-visual');
  if (!settings.showWhy) args.push('--no-diagnostic');
  const id = `j${++jobCounter}`;
  enqueue({ id, deckId, kind: 'repair', args });
  return { jobId: id, reviewDir: dir, output: out };
});

ipcMain.handle('engine:undoSlide', (_e, deckId, mended, slide) => {
  const dir = reviewDir(deckId);
  const id = `j${++jobCounter}`;
  enqueue({ id, deckId, kind: 'undo', args: ['undo-slide', mended, '--prefit', path.join(dir, 'prefit.pptx'),
    '--slide', String(slide), '--review-dir', dir, '--json'] });
  return { jobId: id };
});

ipcMain.handle('engine:cancel', (_e, deckId) => {
  for (let i = jobs.length - 1; i >= 0; i--) if (jobs[i].deckId === deckId) jobs.splice(i, 1);
  if (running && running.deckId === deckId && running.child) { running.cancelled = true; running.child.kill(); }
});

ipcMain.handle('review:load', (_e, deckId) => {
  const f = path.join(reviewDir(deckId), 'review.json');
  try { return { dir: reviewDir(deckId), data: JSON.parse(fs.readFileSync(f, 'utf8')) }; }
  catch (_) { return null; }
});

ipcMain.handle('report:export', async (_e, deckId, deckName) => {
  const src = path.join(reviewDir(deckId), 'report.html');
  if (!fs.existsSync(src)) return { error: 'Repair the deck first: the report is made during repair.' };
  const dest = await dialog.showSaveDialog(mainWindow, {
    defaultPath: path.join(app.getPath('downloads'), `${deckName} - SlideTistic report.html`),
    filters: [{ name: 'Web page', extensions: ['html'] }],
  });
  if (dest.canceled) return { cancelled: true };
  fs.copyFileSync(src, dest.filePath);
  return { path: dest.filePath };
});

ipcMain.handle('media:export', async (_e, file, kind) => {
  const ext = kind === 'xlsx' ? 'xlsx' : 'csv';
  const dest = await dialog.showSaveDialog(mainWindow, {
    defaultPath: path.join(app.getPath('downloads'), `${path.basename(file, path.extname(file))} - media.${ext}`),
    filters: [{ name: ext.toUpperCase(), extensions: [ext] }],
  });
  if (dest.canceled) return { cancelled: true };
  return new Promise((resolve) => {
    const { cmd, args, cwd, env } = engineCommand(['media', file, `--${ext}`, dest.filePath]);
    execFile(cmd, args, { cwd, env }, (err) => resolve(err ? { error: err.message } : { path: dest.filePath }));
  });
});

ipcMain.handle('shell:showInFolder', (_e, p) => shell.showItemInFolder(p));
ipcMain.handle('shell:openPath', (_e, p) => shell.openPath(p));
ipcMain.handle('shell:openExternal', (_e, url) => {
  // Only web links from findings (YouTube, Drive…) and the VEP footer; never file: or custom schemes.
  if (/^https?:\/\//i.test(url)) return shell.openExternal(url);
  return null;
});

// Open a deck in PowerPoint at a given slide.
ipcMain.handle('ppt:openAtSlide', (_e, file, slide) => new Promise((resolve) => {
  if (!isMac) { shell.openPath(file).then(() => resolve({ ok: true, note: 'Opened; jump to the slide by hand on Windows for now.' })); return; }
  const script = `
    tell application "Microsoft PowerPoint"
      activate
      open POSIX file ${JSON.stringify(file)}
      set p to active presentation
      if (full name of p) is ${JSON.stringify(file)} then
        go to slide (view of document window 1) number ${Number(slide)}
      end if
    end tell`;
  execFile('osascript', ['-e', script], (err) => resolve(err ? { ok: false, error: err.message } : { ok: true }));
}));

ipcMain.handle('app:info', () => ({
  version: app.getVersion(), platform: process.platform, logFile: logFile(),
  powerpoint: isMac ? fs.existsSync('/Applications/Microsoft PowerPoint.app') : null,
}));

ipcMain.handle('app:openSlideFluid', () => {
  const candidates = isMac ? ['/Applications/SlideFluid.app']
    : [path.join(process.env.LOCALAPPDATA || '', 'Programs', 'slidefluid', 'SlideFluid.exe')];
  const found = candidates.find((p) => fs.existsSync(p));
  if (!found) return { error: 'SlideFluid isn\'t installed on this computer.' };
  shell.openPath(found);
  return { ok: true };
});

ipcMain.handle('log:tail', (_e, n = 200) => {
  try { return fs.readFileSync(logFile(), 'utf8').split('\n').slice(-n).join('\n'); } catch (_) { return ''; }
});

// ---------------------------------------------------------------------------------------------
// Watch folder: new or changed decks appear in the queue (scanned, not repaired).

let watcher = null;
const watchSeen = new Map();
function startWatching() {
  if (watcher) { watcher.close(); watcher = null; }
  const dir = settings.watchFolder;
  if (!dir || !fs.existsSync(dir)) return;
  const pending = new Map();
  watcher = fs.watch(dir, { recursive: true }, (_event, name) => {
    if (!name || !name.toLowerCase().endsWith('.pptx') || name.includes(settings.suffix) || path.basename(name).startsWith('~$')) return;
    const full = path.join(dir, name);
    clearTimeout(pending.get(full));
    // Wait until the file stops changing (Dropbox/OneDrive write in chunks).
    pending.set(full, setTimeout(() => {
      try {
        const st = fs.statSync(full);
        if (watchSeen.get(full) === st.mtimeMs) return;
        watchSeen.set(full, st.mtimeMs);
        send('watch:found', [{ path: full, name: path.basename(full), size: st.size, isDir: false, ext: '.pptx' }]);
      } catch (_) { /* deleted again */ }
    }, 2500));
  });
}

// ---------------------------------------------------------------------------------------------
// Auto-update (packaged builds only), one status channel to the renderer (global CLAUDE recipe).

function setupUpdater() {
  if (!app.isPackaged) return;
  const { autoUpdater } = require('electron-updater');
  autoUpdater.autoDownload = false;
  autoUpdater.autoInstallOnAppQuit = true;
  autoUpdater.logger = { info: (m) => log('info', '[updater]', m), warn: (m) => log('warn', '[updater]', m), error: (m) => log('error', '[updater]', m) };
  const status = (p) => send('update-status', p);
  autoUpdater.on('checking-for-update', () => status({ type: 'checking' }));
  autoUpdater.on('update-available', (i) => status({ type: 'available', version: i.version }));
  autoUpdater.on('update-not-available', () => status({ type: 'not-available' }));
  autoUpdater.on('download-progress', (p) => status({ type: 'progress', percent: p.percent, bytesPerSecond: p.bytesPerSecond, transferred: p.transferred, total: p.total }));
  autoUpdater.on('update-downloaded', (i) => status({ type: 'downloaded', version: i.version }));
  autoUpdater.on('error', (err) => status({ type: 'error', message: (err && err.message) || String(err) }));
  ipcMain.handle('update:check', () => autoUpdater.checkForUpdates());
  ipcMain.handle('update:download', () => autoUpdater.downloadUpdate());
  ipcMain.on('update:install', () => autoUpdater.quitAndInstall());
  setTimeout(() => autoUpdater.checkForUpdates(), 60000);   // atom-feed cache lag: wait a minute
}

// ---------------------------------------------------------------------------------------------

function createWindow() {
  const { width, height } = settings.window || DEFAULTS.window;
  mainWindow = new BrowserWindow({
    width, height, minWidth: 980, minHeight: 640,
    backgroundColor: '#070910',
    title: 'SlideTistic',
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false },
  });
  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));
  mainWindow.on('close', () => {
    const [w, h] = mainWindow.getSize();
    settings.window = { width: w, height: h };
    saveSettings();
  });
}

app.whenReady().then(() => {
  settings = loadSettings();
  createWindow();
  startWatching();
  setupUpdater();
  log('info', 'started', app.getVersion(), os.platform());
});
app.on('window-all-closed', () => app.quit());
