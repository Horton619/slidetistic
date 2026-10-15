// The renderer's whole view of the outside world: window.slidetistic.
// Listeners return an unsubscribe function (SlideFluid pattern).

const { contextBridge, ipcRenderer, webUtils } = require('electron');

function listen(channel, cb) {
  const handler = (_e, payload) => cb(payload);
  ipcRenderer.on(channel, handler);
  return () => ipcRenderer.removeListener(channel, handler);
}

contextBridge.exposeInMainWorld('slidetistic', {
  // settings
  getSettings: () => ipcRenderer.invoke('settings:getAll'),
  setSetting: (key, value) => ipcRenderer.invoke('settings:set', key, value),

  // files
  pathForFile: (file) => webUtils.getPathForFile(file),          // drag-and-drop File → path
  pickFiles: () => ipcRenderer.invoke('dialog:openFiles'),
  pickFolder: () => ipcRenderer.invoke('dialog:openFolder'),
  expand: (paths) => ipcRenderer.invoke('files:expand', paths),

  // engine
  listChecks: () => ipcRenderer.invoke('engine:listChecks'),
  scan: (deckId, file, opts) => ipcRenderer.invoke('engine:scan', deckId, file, opts),
  repair: (deckId, file, opts) => ipcRenderer.invoke('engine:repair', deckId, file, opts),
  undoSlide: (deckId, mended, slide) => ipcRenderer.invoke('engine:undoSlide', deckId, mended, slide),
  cancel: (deckId) => ipcRenderer.invoke('engine:cancel', deckId),
  loadReview: (deckId) => ipcRenderer.invoke('review:load', deckId),
  discardReview: (deckId) => ipcRenderer.invoke('review:discard', deckId),
  tempSize: () => ipcRenderer.invoke('temp:size'),
  collectFonts: (file) => ipcRenderer.invoke('fonts:collect', file),
  getFonts: (file, families) => ipcRenderer.invoke('fonts:get', file, families),
  adobeFonts: (families) => ipcRenderer.invoke('fonts:adobe', families),
  activateFonts: (deckId, items) => ipcRenderer.invoke('fonts:activate', deckId, items),
  activateNext: () => ipcRenderer.invoke('fonts:activateNext'),
  activateStop: () => ipcRenderer.invoke('fonts:activateStop'),
  onFontActivation: (cb) => listen('fonts:activation', cb),
  loadChecked: (key) => ipcRenderer.invoke('checked:load', key),
  setChecked: (key, slide, sig) => ipcRenderer.invoke('checked:set', key, slide, sig),
  vote: (record) => ipcRenderer.invoke('feedback:vote', record),
  loadVotes: (deckSha) => ipcRenderer.invoke('feedback:load', deckSha),
  clearTemp: (keepIds) => ipcRenderer.invoke('temp:clear', keepIds),
  onEngineEvent: (cb) => listen('engine:event', cb),

  // outputs
  exportReport: (deckId, deckName) => ipcRenderer.invoke('report:export', deckId, deckName),
  exportMedia: (file, kind) => ipcRenderer.invoke('media:export', file, kind),
  showInFolder: (p) => ipcRenderer.invoke('shell:showInFolder', p),
  openPath: (p) => ipcRenderer.invoke('shell:openPath', p),
  openExternal: (url) => ipcRenderer.invoke('shell:openExternal', url),
  openAtSlide: (file, slide) => ipcRenderer.invoke('ppt:openAtSlide', file, slide),

  // app
  info: () => ipcRenderer.invoke('app:info'),
  openSlideFluid: () => ipcRenderer.invoke('app:openSlideFluid'),
  logTail: (n) => ipcRenderer.invoke('log:tail', n),
  onWatchFound: (cb) => listen('watch:found', cb),

  // updates
  checkForUpdate: () => ipcRenderer.invoke('update:check'),
  downloadUpdate: () => ipcRenderer.invoke('update:download'),
  installUpdate: () => ipcRenderer.send('update:install'),
  moveToApplications: () => ipcRenderer.invoke('app:moveToApplications'),
  onUpdateStatus: (cb) => listen('update-status', cb),
});
