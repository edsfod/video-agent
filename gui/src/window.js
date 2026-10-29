// The window and the tray.

const { BrowserWindow, nativeTheme, shell, app, Menu, nativeImage, Tray } = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const shared = require('./shared');
const { send } = shared;
const { loadSettings } = require('./settings');

const ICONS = path.join(__dirname, '..', 'assets');

// What the tray shows, kept for the end-to-end tests, which read it through app.evaluate.
/** @type {{ tooltip: string, menu: Electron.Menu | null }} */
const trayState = { tooltip: '', menu: null };
global.vaTray = {
  tooltip: () => trayState.tooltip,
  labels: () => trayState.menu?.items.map((item) => item.label).filter(Boolean) ?? [],
  click: (label) => trayState.menu?.items.find((item) => item.label === label)?.click(),
  windowVisible: () => !!shared.win && !shared.win.isDestroyed() && shared.win.isVisible(),
};

// The GUI tests set this so their windows are never seen: off the screen, without a taskbar button, shown without
// taking the focus (user request, 2026-10-29: test windows took the focus, then still came up on top).
const BACKGROUND = !!process.env.VA_E2E_BACKGROUND;

function createWindow() {
  const win = new BrowserWindow({
    show: !BACKGROUND,
    ...(BACKGROUND ? { x: -32000, y: -32000, skipTaskbar: true } : {}),
    width: 1280,
    height: 820,
    minWidth: 960,
    minHeight: 600,
    title: 'Video Agent',
    icon: path.join(ICONS, 'icon-256.png'),
    backgroundColor: nativeTheme.shouldUseDarkColors ? '#1b1a18' : '#faf9f7',
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, sandbox: true },
  });
  shared.win = win;
  win.removeMenu();
  if (BACKGROUND) win.showInactive();
  win.on('close', (event) => {
    if (shared.quitting || !loadSettings().closeToTray || !shared.tray) return;
    event.preventDefault();
    win.hide();
  });
  win.loadFile(path.join(__dirname, 'renderer', 'index.html'));
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//.test(url)) shell.openExternal(url);
    return { action: 'deny' };
  });
  win.webContents.on('will-navigate', (event) => event.preventDefault());

  // --screenshot=<file> [--select=<n>] [--tab=<name>]: render, save a PNG and quit (for checks without a person).
  const option = (name) => process.argv.find((arg) => arg.startsWith(`--${name}=`))?.split('=').slice(1).join('=');
  const target = option('screenshot');
  if (target) {
    if (option('theme')) nativeTheme.themeSource = /** @type {'light' | 'dark'} */ (option('theme')); // light or dark
    win.webContents.once('did-finish-load', async () => {
      await win.webContents.executeJavaScript(
        `window.__screenshot && window.__screenshot(${JSON.stringify({ select: option('select'), tab: option('tab') })})`,
      );
      await new Promise((resolve) => setTimeout(resolve, Number(option('wait') || 2500)));
      // Wait for the images in view to finish decoding (at most 10 s); lazy ones below the fold never start.
      await win.webContents.executeJavaScript(`Promise.race([
        Promise.all([...document.images].filter((image) => {
          const box = image.getBoundingClientRect();
          return image.src && box.top < innerHeight && box.bottom > 0;
        }).map((image) => image.decode().catch(() => {}))),
        new Promise((resolve) => setTimeout(resolve, 10000)),
      ])`);
      // Wait for two painted frames; capturing right after the timer can return a stale frame.
      await win.webContents.executeJavaScript(
        'new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))',
      );
      fs.writeFileSync(target, (await win.webContents.capturePage()).toPNG());
      app.quit();
    });
  }
}

function showWindow() {
  if (!shared.win || shared.win.isDestroyed()) return createWindow();
  if (shared.win.isMinimized()) shared.win.restore();
  if (BACKGROUND) return shared.win.showInactive();
  shared.win.show();
  shared.win.focus();
}

function updateTray() {
  if (!shared.tray) return;
  const running = shared.queue.list().filter((task) => task.status === 'running').map((task) => task.title);
  const waiting = shared.queue.list().filter((task) => task.status === 'queued').length;
  trayState.tooltip = running.length ? `Video Agent · 正在运行：${running.join('；')}` : 'Video Agent';
  shared.tray.setToolTip(trayState.tooltip);
  shared.tray.setContextMenu(
    (trayState.menu = Menu.buildFromTemplate([
      { label: '显示窗口', click: showWindow },
      { label: '添加本地视频…', click: () => (showWindow(), send('tray:add-videos')) },
      { type: 'separator' },
      { label: running.length ? `正在运行 ${running.length} 个任务${waiting ? `，排队 ${waiting} 个` : ''}` : '没有运行中的任务', enabled: false },
      { label: '停止所有任务', enabled: running.length + waiting > 0, click: () => shared.queue.cancelAll() },
      { type: 'separator' },
      { label: '打开工作区', click: () => shell.openPath(loadSettings().workspace) },
      { label: '打开日志文件夹', click: () => shell.openPath(shared.logs.dir) },
      { type: 'separator' },
      { label: '退出', click: () => app.quit() },
    ])),
  );
}

function createTray() {
  const image = nativeImage.createFromPath(path.join(ICONS, 'icon-16.png'));
  image.addRepresentation({ scaleFactor: 2, buffer: fs.readFileSync(path.join(ICONS, 'icon-32.png')) });
  shared.tray = new Tray(image);
  shared.tray.on('click', showWindow);
  updateTray();
}

module.exports = { createTray, createWindow, showWindow, updateTray };
