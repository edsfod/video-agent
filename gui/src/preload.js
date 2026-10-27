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
  env: () => ipcRenderer.invoke('env:info'),
  installPlugin: (agent) => ipcRenderer.invoke('plugin:install', agent),
  pickVideos: () => ipcRenderer.invoke('dialog:videos'),
  pickFolder: (title) => ipcRenderer.invoke('dialog:folder', title),
  droppedPath: (file) => webUtils.getPathForFile(file),

  startCli: (id, args, stdin, title) => ipcRenderer.invoke('cli:start', { id, args, stdin, title }),
  cliJson: (args) => ipcRenderer.invoke('cli:json', args),
  cliText: (args, stdin) => ipcRenderer.invoke('cli:text', { args, stdin }),
  startAgent: (options) => ipcRenderer.invoke('agent:start', options),
  cancel: (id) => ipcRenderer.invoke('job:cancel', id),
  onJobOutput: listen('job:output'),
  onJobExit: listen('job:exit'),

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
