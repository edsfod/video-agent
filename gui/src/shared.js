// What the main process's modules share: the window, the tray, the logs, the updater, the task queue, the running
// jobs and terminals, all set at start (main.js); and sending to the window.

const shared = {
  /** @type {Electron.BrowserWindow | null} */
  win: null,
  /** @type {Electron.Tray | null} */
  tray: null,
  /** @type {import('./logs').Logs} */
  logs: /** @type {any} */ (null), // set first thing at start
  /** @type {ReturnType<typeof import('./updater').createUpdater>} */
  updater: /** @type {any} */ (null),
  /** @type {import('./tasks').TaskQueue} */
  queue: /** @type {any} */ (null),
  quitting: false,
  jobs: new Map(), // running child processes by task id
  terminals: new Map(),
};

function send(channel, value) {
  if (shared.win && !shared.win.isDestroyed()) shared.win.webContents.send(channel, value);
}

module.exports = Object.assign(shared, { send });
