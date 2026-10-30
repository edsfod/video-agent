// Electron main process: runs the Video Agent CLI, the Agent CLIs and terminal shells for the window.
// All media and summary work happens in the CLI; this process only starts processes and relays their output.

const { app, nativeTheme } = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const shared = require('./shared');
const accounts = require('./accounts');
const { Logs } = require('./logs');
const { createUpdater } = require('./updater');
const { THEMES, cookiesDir, loadSettings, saveSettings } = require('./settings');
const { createQueue } = require('./jobs');
const { refreshPluginsAfterUpdate } = require('./plugins');
const { registerIpc } = require('./ipc');
const { createTray, createWindow, showWindow } = require('./window');

// The cookie export, for the end-to-end tests, which call it through app.evaluate.
global.vaAccounts = { writeCookies: (key, file) => accounts.writeCookies(key, file) };

// Windows tells Chromium which windows other windows cover, and a covered, minimised or off-screen page then draws
// nothing, not even DeepSeek's answer as it streams in, which deepseek.js reads from the page (user report,
// 2026-10-30: answers read back incomplete while the DeepSeek window was behind the main one). With this off, and
// throttling off in that window, it draws as if in front.
app.commandLine.appendSwitch('disable-features', 'CalculateNativeWinOcclusion');

// --user-data=<dir> keeps test runs away from the user's settings.
const userData = process.argv.find((arg) => arg.startsWith('--user-data='));
if (userData) app.setPath('userData', userData.slice('--user-data='.length));

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', showWindow);
  app.whenReady().then(() => {
    shared.logs = new Logs(path.join(app.getPath('userData'), 'logs'));
    shared.logs.line('info', `started ${app.getVersion()}, Electron ${process.versions.electron}`);
    process.on('uncaughtException', (error) => shared.logs.line('error', error.stack || String(error)));
    fs.mkdirSync(loadSettings().workspace, { recursive: true });
    fs.rmSync(cookiesDir(), { recursive: true, force: true });
    createQueue();
    shared.updater = createUpdater({ logs: shared.logs, send: shared.send, settings: loadSettings, remember: saveSettings, running: () => shared.queue.active().length });
    registerIpc();
    createTray();
    nativeTheme.themeSource = THEMES.includes(loadSettings().theme) ? loadSettings().theme : 'system';
    createWindow();
    if (app.isPackaged) refreshPluginsAfterUpdate().catch((error) => shared.logs.line('warn', `plugin refresh: ${error.message}`));
    // One quiet check a little after start; it only tells the window, it downloads nothing.
    if (loadSettings().checkUpdates !== false && (app.isPackaged || process.env.VA_UPDATE_ROOT)) {
      setTimeout(() => shared.updater.check().catch(() => {}), Number(process.env.VA_UPDATE_DELAY_MS || 8000));
    }
  });
}

app.on('before-quit', () => (shared.quitting = true));
app.on('will-quit', () => {
  shared.queue?.cancelAll();
  for (const term of shared.terminals.values()) term.kill();
  shared.logs?.line('info', 'quit');
});
app.on('window-all-closed', () => app.quit());
