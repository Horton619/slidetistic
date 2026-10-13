// SlideTistic — Electron main process.
// The engine is a Python CLI (`engine.cli`) run as a subprocess that prints one JSON object per line
// (SlideFluid's NDJSON pattern). Jobs run one at a time: PowerPoint can only render one deck at once.

const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const fs = require('fs');
const os = require('os');
const { spawn, execFile, execFileSync } = require('child_process');

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
  shapeCache: true,
  hidePowerPoint: true,        // Mac: keep PowerPoint hidden while rendering (when SlideTistic started it)            // Diagnostics: remember shape lists between edits (off = slower, the pre-0.4.1 way)
  crewFonts: '',               // one per line
  skin: 'pro',
  showWhy: true,               // diagnostic mode: the rule behind each call
  watchFolder: '',
  presets: {},                 // { canva: { F001: {check:true, fix:true}, … }, … }
  lastTab: 'review',
  tuningMode: false,           // Diagnostics: 👍/👎 on changed slides, for tuning the layout rules (David)
  feedbackFolder: '',          // '' = the shared Dropbox suite's _feedback, else userData/feedback
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

// A job that reports nothing for this long is stuck (a hung network read was seen on Windows); it is
// stopped and the queue moves on. Longer than the renderer's own 300 s PowerPoint timeout, since a
// scan's render runs inside one check step with no events.
const STALL_MS = { scan: 6 * 60e3, repair: 10 * 60e3, undo: 10 * 60e3 };

// Jobs the user clicked (repair, undo) go ahead of queued scans, in click order, and stop a running
// scan, which goes back to the front of the scans. Repair is only offered on a scanned deck, so it
// never jumps its own deck's scan. A scan that is mid-render is left to finish: killing the engine
// then would leave its hidden copy open in PowerPoint.
function enqueue(job) {
  const firstScan = job.kind === 'scan' ? -1 : jobs.findIndex((j) => j.kind === 'scan');
  if (firstScan < 0) jobs.push(job); else jobs.splice(firstScan, 0, job);
  send('engine:event', { jobId: job.id, deckId: job.deckId, type: 'queued', kind: job.kind });
  if (job.kind !== 'scan' && running && running.kind === 'scan' && running.child
      && running.stage !== 'render' && !running.preempted) {
    running.preempted = true;
    running.child.kill();
  }
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
  let stalled = false;
  let watchdog;
  const alive = () => {
    clearTimeout(watchdog);
    watchdog = setTimeout(() => { stalled = true; child.kill(); }, STALL_MS[job.kind] || STALL_MS.repair);
  };
  alive();
  let buf = '';
  let stderr = '';
  child.stdout.on('data', (d) => {
    alive();
    buf += d.toString();
    let i;
    while ((i = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, i).trim();
      buf = buf.slice(i + 1);
      if (!line.startsWith('{')) continue;
      try {
        const ev = JSON.parse(line);
        if (ev.type === 'error' || ev.type === 'warn') log(ev.type, job.kind, ev.message || '');
        if (ev.type === 'progress') job.stage = ev.stage;
        send('engine:event', { jobId: job.id, deckId: job.deckId, kind: job.kind, ...ev });
      } catch (_) { /* partial or non-JSON line */ }
    }
  });
  child.stderr.on('data', (d) => { alive(); stderr += d.toString(); });
  child.on('close', (code) => {
    clearTimeout(watchdog);
    running = null;
    if (job.preempted && !job.cancelled) {
      // Stopped for a repair: run it again first among the scans. The card stays "waiting".
      log('info', 'engine', 'scan paused for a repair', job.deckId);
      const again = { id: job.id, deckId: job.deckId, kind: 'scan', args: job.args };
      const firstScan = jobs.findIndex((j) => j.kind === 'scan');
      if (firstScan < 0) jobs.push(again); else jobs.splice(firstScan, 0, again);
      send('engine:event', { jobId: job.id, deckId: job.deckId, kind: 'scan', type: 'requeued' });
      pump();
      return;
    }
    if (stalled && !job.cancelled) {
      const mins = Math.round((STALL_MS[job.kind] || STALL_MS.repair) / 60e3);
      const message = `Stopped: no progress for ${mins} minutes. The file may be on a slow or unreachable drive; `
        + 'copy it to this computer and try again.';
      log('error', job.kind, 'stalled', job.deckId, job.args[1] || '');
      send('engine:event', { jobId: job.id, deckId: job.deckId, kind: job.kind, type: 'error', message });
      code = code || 1;
    }
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
  if (settings.shapeCache === false) a.push('--shape-cache', 'off');
  if (isMac && settings.hidePowerPoint === false) a.push('--powerpoint-visible');
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

// --- temporary files: review bundles (slide images + a pre-fit copy of each repaired deck) and the
// engine's PowerPoint work folders. Automatic: review bundles are cleared at launch (the queue isn't
// kept between launches) and when a deck leaves the queue; the engine clears work folders over 6 h old
// whenever it renders. Manual: Settings → Diagnostics → Clear now.
const reviewsRoot = () => path.join(app.getPath('userData'), 'reviews');
const renderWorkRoots = () => (isMac
  ? [path.join(os.homedir(), 'Library/Containers/com.microsoft.Powerpoint/Data/tmp/slidetistic')]
  : [path.join(os.tmpdir(), 'slidetistic')]);

function folderBytes(dir) {
  let total = 0;
  let entries = [];
  try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch (_) { return 0; }
  for (const e of entries) {
    const p = path.join(dir, e.name);
    try { total += e.isDirectory() ? folderBytes(p) : fs.statSync(p).size; } catch (_) { /* vanished */ }
  }
  return total;
}

function clearReviews(keepIds = []) {
  let entries = [];
  try { entries = fs.readdirSync(reviewsRoot()); } catch (_) { return; }
  for (const id of entries) if (!keepIds.includes(id)) fs.rmSync(path.join(reviewsRoot(), id), { recursive: true, force: true });
}

ipcMain.handle('temp:size', () => ({
  bytes: folderBytes(reviewsRoot()) + renderWorkRoots().reduce((n, d) => n + folderBytes(d), 0),
}));
ipcMain.handle('temp:clear', (_e, keepIds = []) => new Promise((resolve) => {
  clearReviews(keepIds);
  const { cmd, args, cwd, env } = engineCommand(['cleanup', '--all', '--json']);
  execFile(cmd, args, { cwd, env }, (err) => {
    if (err) log('warn', 'cleanup', err.message);
    resolve({ bytes: folderBytes(reviewsRoot()) + renderWorkRoots().reduce((n, d) => n + folderBytes(d), 0) });
  });
}));
ipcMain.handle('review:discard', (_e, deckId) => {
  if (/^d\d+$/.test(String(deckId))) fs.rmSync(reviewDir(deckId), { recursive: true, force: true });
});

ipcMain.handle('review:load', (_e, deckId) => {
  const f = path.join(reviewDir(deckId), 'review.json');
  try { return { dir: reviewDir(deckId), data: JSON.parse(fs.readFileSync(f, 'utf8')) }; }
  catch (_) { return null; }
});

// ---------------------------------------------------------------------------------------------
// Tuning votes (David 2026-10-11): one JSON line per vote, one file per machine so the Mac and the PC
// never write the same Dropbox file. `slidetistic tune` reads them. No slide text is stored.

function feedbackDir() {
  if (settings.feedbackFolder) return settings.feedbackFolder;
  const home = app.getPath('home');
  const suites = [path.join(home, 'Library', 'CloudStorage', 'Dropbox', 'SlideTistic Test Suite'),
                  path.join(home, 'Dropbox', 'SlideTistic Test Suite')];
  const suite = suites.find((p) => fs.existsSync(p));
  return suite ? path.join(suite, '_feedback') : path.join(app.getPath('userData'), 'feedback');
}
const machineName = () => os.hostname().replace(/\.local(domain)?$/i, '').replace(/[^\w.-]+/g, '-');

function readVotes() {
  const dir = feedbackDir();
  let files = [];
  try { files = fs.readdirSync(dir).filter((f) => /^votes-.*\.jsonl$/.test(f)); } catch (_) { return []; }
  const rows = [];
  for (const f of files) {
    let text = '';
    try { text = fs.readFileSync(path.join(dir, f), 'utf8'); } catch (_) { continue; }
    for (const line of text.split('\n')) {
      if (!line.trim()) continue;
      try { rows.push(JSON.parse(line)); } catch (_) { /* a half-synced last line */ }
    }
  }
  rows.sort((a, b) => String(a.t).localeCompare(String(b.t)));
  const latest = new Map();
  for (const r of rows) latest.set(`${r.deck_sha12}|${r.slide}|${r.tuning_sig}`, r);
  return [...latest.values()].filter((r) => r.vote === 'up' || r.vote === 'down');
}

ipcMain.handle('feedback:vote', (_e, record) => {
  const dir = feedbackDir();
  const row = { t: new Date().toISOString(), machine: machineName(), app: app.getVersion(), ...record };
  try {
    fs.mkdirSync(dir, { recursive: true });
    fs.appendFileSync(path.join(dir, `votes-${machineName()}.jsonl`), JSON.stringify(row) + '\n');
    return { ok: true };
  } catch (err) {
    log('error', 'vote not saved', err.message);
    return { error: err.message };
  }
});

ipcMain.handle('feedback:load', (_e, deckSha) => {
  const all = readVotes();
  const up = all.filter((r) => r.vote === 'up').length;
  return { dir: feedbackDir(), total: all.length, up, deck: all.filter((r) => r.deck_sha12 === deckSha) };
});

// "✓ Checked" marks on broken (red) slides (David 2026-10-12): kept per deck fingerprint, so reopening the
// same deck shows what the operator already went through. A slide's mark only counts while its red
// findings are the ones that were checked (the renderer passes their signature).
const checkedFile = () => path.join(app.getPath('userData'), 'checked-slides.json');
function readChecked() {
  try { return JSON.parse(fs.readFileSync(checkedFile(), 'utf8')); } catch (_) { return {}; }
}
ipcMain.handle('checked:load', (_e, key) => readChecked()[key] || {});
ipcMain.handle('checked:set', (_e, key, slide, sig) => {
  const all = readChecked();
  const marks = { ...(all[key] || {}) };
  if (sig) marks[slide] = { sig, t: new Date().toISOString() }; else delete marks[slide];
  all[key] = marks;
  try {
    fs.writeFileSync(checkedFile(), JSON.stringify(all));
    return { ok: true };
  } catch (err) {
    log('error', 'checked mark not saved', err.message);
    return { error: err.message };
  }
});

// Free fonts (F009, David 2026-10-12). No PowerPoint involved, so these run beside the job queue.
function engineJson(cliArgs, timeout) {
  return new Promise((resolve) => {
    const { cmd, args, cwd, env } = engineCommand(cliArgs);
    execFile(cmd, args, { cwd, env, timeout, maxBuffer: 20 * 1024 * 1024 }, (err, stdout, stderr) => {
      const events = String(stdout || '').split('\n').filter((l) => l.trim().startsWith('{')).map((l) => {
        try { return JSON.parse(l); } catch (_) { return null; }
      }).filter(Boolean);
      if (err && !events.length) log('error', cliArgs.slice(0, 2).join(' '), err.message, String(stderr || '').slice(-400));
      resolve({ events, error: err && !events.length ? (String(stderr || '').trim().split('\n').pop() || err.message) : null });
    });
  });
}
ipcMain.handle('fonts:get', async (_e, file, families) => {
  const r = await engineJson(['fonts', 'get', file, '--install', '--json', ...families.flatMap((f) => ['--family', f])], 5 * 60e3);
  log('info', 'fonts get', families.join(', '), r.events.filter((e) => e.type === 'font').map((e) => e.message).join(' | '));
  return r;
});
// Testing aid (David 2026-10-12): the deck's fonts in '<deck> - fonts' next to it, named by what they are;
// installed / Creative Cloud fonts copied, free ones downloaded. Then show the folder in Finder/Explorer.
ipcMain.handle('fonts:collect', async (_e, file) => {
  const r = await engineJson(['fonts', 'collect', file, '--json'], 5 * 60e3);
  const done = r.events.find((e) => e.type === 'done');
  if (done?.folder) shell.showItemInFolder(path.join(done.folder, 'FONTS.txt'));
  return { ...r, folder: done?.folder || null };
});
function refreshFontCatalog() {
  engineJson(['fonts', 'catalog', '--json'], 60e3).then((r) => {
    const ev = r.events[0];
    if (ev) log(ev.type === 'error' ? 'warn' : 'info', 'font catalog:', ev.message);
  });
}

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
// Windows: open in the user's PowerPoint (visible, stays open) and jump to the slide. Only the
// presentation our Open returned is touched; the path travels in an env var, never inside the script.
const WIN_OPEN_AT_SLIDE = [
  '$ErrorActionPreference = "Stop"',
  '$app = New-Object -ComObject PowerPoint.Application',
  '$app.Visible = -1',
  '$p = $app.Presentations.Open($env:ST_FILE)',
  'if ($p.FullName -ne $env:ST_FILE) { throw "PowerPoint opened a different file" }',
  '$w = $p.Windows.Item(1)',
  '$w.View.GotoSlide([int]$env:ST_SLIDE)',
  '$w.Activate()',
].join('; ');

ipcMain.handle('ppt:openAtSlide', (_e, file, slide) => new Promise((resolve) => {
  if (!isMac) {
    execFile('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', WIN_OPEN_AT_SLIDE],
      { env: { ...process.env, ST_FILE: path.resolve(file), ST_SLIDE: String(Number(slide) || 1) }, timeout: 60000 },
      (err) => {
        if (!err) { resolve({ ok: true }); return; }
        log('warn', 'openAtSlide', err.message);
        shell.openPath(file).then(() => resolve({ ok: true, note: 'Opened; jump to the slide by hand.' }));
      });
    return;
  }
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

// Windows: the same registry key the engine's renderer checks (PowerPoint.Application registered for COM).
function windowsHasPowerPoint() {
  try {
    execFileSync('reg', ['query', 'HKCR\\PowerPoint.Application\\CLSID'], { stdio: 'ignore', timeout: 10000 });
    return true;
  } catch (_) { return false; }
}

ipcMain.handle('app:info', () => ({
  version: app.getVersion(), platform: process.platform, logFile: logFile(),
  powerpoint: isMac ? fs.existsSync('/Applications/Microsoft PowerPoint.app')
    : process.platform === 'win32' ? windowsHasPowerPoint() : null,
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
  ipcMain.on('update:install', () => {
    // A copy macOS won't let us overwrite can't install: say so instead of a Restart button that does nothing
    // (David 2026-10-12: 0.4.0 ran from Downloads, "translocated"; Squirrel refused the swap).
    const where = placementProblem();
    if (where) { status({ type: 'move-needed', where }); return; }
    autoUpdater.quitAndInstall();
  });
  ipcMain.handle('app:moveToApplications', () => {
    try {
      return { ok: app.moveToApplicationsFolder({ conflictHandler: () => true }) };   // relaunches from /Applications
    } catch (err) {
      log('error', 'move to Applications', err.message);
      return { error: err.message };
    }
  });
  // Launch: a copy outside Applications can't update itself, so offer the move before anything is downloaded.
  setTimeout(() => { const where = placementProblem(); if (where) status({ type: 'move-needed', where }); }, 3000);
  setTimeout(() => autoUpdater.checkForUpdates(), 60000);   // atom-feed cache lag: wait a minute
}

// Mac: SlideTistic opened from the disk image or Downloads runs from a read-only copy ("App Translocation") and
// can never install an update. null when it's fine (in Applications, or not a Mac).
function placementProblem() {
  if (!isMac || !app.isPackaged) return null;
  if (app.isInApplicationsFolder()) return null;
  const exe = app.getPath('exe');
  return exe.includes('/AppTranslocation/') ? 'translocated' : exe.startsWith('/Volumes/') ? 'disk image' : 'outside Applications';
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
  clearReviews();          // last session's queue is gone, so are its review bundles
  createWindow();
  startWatching();
  setupUpdater();
  log('info', 'started', app.getVersion(), os.platform());
  setTimeout(refreshFontCatalog, 20e3);      // weekly free-font list; never during a scan's first moments
});
app.on('window-all-closed', () => app.quit());
