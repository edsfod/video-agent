// The only bridge between the page and the main process; the page has no Node access.

const { contextBridge, ipcRenderer, webUtils } = require('electron');

const listen = (channel) => (callback) => {
  const handler = (_, value) => callback(value);
  ipcRenderer.on(channel, handler);
  return () => ipcRenderer.removeListener(channel, handler);
};

contextBridge.exposeInMainWorld('va', {
  settings: () => ipcRenderer.invoke('settings:get'),
  saveSettings: (changes) => ipcRenderer.invoke('settings:set', changes),
  previewTheme: (theme) => ipcRenderer.invoke('theme:preview', theme),
  env: () => ipcRenderer.invoke('env:info'),
  installPlugin: (agent) => ipcRenderer.invoke('plugin:install', agent),
  readSkill: () => ipcRenderer.invoke('skill:read'),
  accounts: () => ipcRenderer.invoke('accounts:list'),
  accountLogin: (key) => ipcRenderer.invoke('accounts:login', key),
  accountLogout: (key) => ipcRenderer.invoke('accounts:logout', key),
  accountImport: (key) => ipcRenderer.invoke('accounts:import', key),
  browsers: () => ipcRenderer.invoke('accounts:browsers'),
  accountFromBrowser: (key, browser) => ipcRenderer.invoke('accounts:from-browser', key, browser),
  updateState: () => ipcRenderer.invoke('update:state'),
  checkUpdate: () => ipcRenderer.invoke('update:check'),
  downloadUpdate: () => ipcRenderer.invoke('update:download'),
  installUpdate: (force) => ipcRenderer.invoke('update:install', force),
  onUpdateState: listen('update:state'),
  pickVideos: () => ipcRenderer.invoke('dialog:videos'),
  pickFolder: (title) => ipcRenderer.invoke('dialog:folder', title),
  pickFile: (title, filters) => ipcRenderer.invoke('dialog:file', { title, filters }),
  pickSave: (title, name) => ipcRenderer.invoke('dialog:save', { title, name }),
  droppedPath: (file) => webUtils.getPathForFile(file),

  addTask: (spec) => ipcRenderer.invoke('tasks:add', spec),
  tasks: () => ipcRenderer.invoke('tasks:list'),
  taskOutput: (id) => ipcRenderer.invoke('tasks:output', id),
  cancelTask: (id) => ipcRenderer.invoke('tasks:cancel', id),
  retryTask: (id) => ipcRenderer.invoke('tasks:retry', id),
  models: (route) => ipcRenderer.invoke('models:list', route),
  installSkill: (target) => ipcRenderer.invoke('skill:install', target),
  clearTasks: () => ipcRenderer.invoke('tasks:clear'),
  onTasks: listen('tasks:changed'),
  onJobOutput: listen('job:output'),
  cliJson: (args) => ipcRenderer.invoke('cli:json', args),
  cliText: (args, stdin) => ipcRenderer.invoke('cli:text', { args, stdin }),

  read: (file) => ipcRenderer.invoke('fs:read', file),
  open: (target) => ipcRenderer.invoke('shell:open', target),
  reveal: (target) => ipcRenderer.invoke('shell:reveal', target),
  external: (url) => ipcRenderer.invoke('shell:external', url),
  copy: (text) => ipcRenderer.invoke('clipboard:write', text),

  logs: () => ipcRenderer.invoke('logs:list'),
  readLog: (file) => ipcRenderer.invoke('logs:read', file),
  openLogs: () => ipcRenderer.invoke('logs:open'),
  logError: (message) => ipcRenderer.send('log:renderer', String(message)),
  onTrayAddVideos: listen('tray:add-videos'),

  ptyStart: (options) => ipcRenderer.invoke('pty:start', options),
  ptyWrite: (id, data) => ipcRenderer.send('pty:write', { id, data }),
  ptyResize: (id, cols, rows) => ipcRenderer.send('pty:resize', { id, cols, rows }),
  ptyKill: (id) => ipcRenderer.invoke('pty:kill', id),
  onPtyData: listen('pty:data'),
  onPtyExit: listen('pty:exit'),
});
