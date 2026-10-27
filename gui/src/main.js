// Electron main process: runs the Video Agent CLI, the Agent CLIs and terminal shells for the window.
// All media and summary work happens in the CLI; this file only starts processes and relays their output.

const { app, BrowserWindow, ipcMain, dialog, shell, clipboard, nativeTheme, Tray, Menu, nativeImage } = require('electron');
const { spawn, execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const pty = require('node-pty');
const { Logs } = require('./logs');
const { createUpdater } = require('./updater');
const bilibili = require('./bilibili');
const { TaskQueue, DEFAULT_LIMITS } = require('./tasks');

const VERSION = app.getVersion(); // package.json, kept equal to the CLI version
// Last resort in development when no CLI is installed: the release wheel through uvx (needs uv, not git).
const UVX_CLI = [
  'uvx', '--from',
  `https://github.com/edsfod/video-agent/releases/download/v${VERSION}/video_agent-${VERSION}-py3-none-any.whl`,
  'video-agent',
];
const settingsFile = () => path.join(app.getPath('userData'), 'settings.json');
// Cookies exported for one download at a time; removed when the download ends and at start (after a crash).
const cookiesDir = () => path.join(app.getPath('userData'), 'cookies');
const jobs = new Map(); // running child processes by task id
let queue;
const terminals = new Map();
const ICONS = path.join(__dirname, '..', 'assets');
let win;
let tray;
let logs;
let updater;
let quitting = false;
// What the tray shows, kept for the end-to-end tests, which read it through app.evaluate.
const trayState = { tooltip: '', menu: null };
global.vaTray = {
  tooltip: () => trayState.tooltip,
  labels: () => trayState.menu?.items.map((item) => item.label).filter(Boolean) ?? [],
  click: (label) => trayState.menu?.items.find((item) => item.label === label)?.click(),
  windowVisible: () => !!win && !win.isDestroyed() && win.isVisible(),
};
// The cookie export, for the same tests.
global.vaBilibili = { writeCookies: (file) => bilibili.writeCookies(file) };

// --user-data=<dir> keeps test runs away from the user's settings.
const userData = process.argv.find((arg) => arg.startsWith('--user-data='));
if (userData) app.setPath('userData', userData.slice('--user-data='.length));

// ---------- settings ----------

function defaults() {
  return {
    workspace: path.join(app.getPath('documents'), 'Video Agent'),
    cli: '',
    videos: [],
    frameInterval: 60,
    maxFrames: null, // representative frames: no fixed cap unless the user sets one
    shell: '',
    closeToTray: true,
    checkUpdates: true,
    updateMirror: '',
    limits: DEFAULT_LIMITS, // tasks of each kind that may run at once (see tasks.js)
  };
}

function loadSettings() {
  let saved;
  try {
    saved = JSON.parse(fs.readFileSync(settingsFile(), 'utf8'));
  } catch {
    return defaults();
  }
  // Up to 0.2.0 every processing run saved the old fixed cap of 36 frames; it was not a choice, so it no longer caps.
  if (saved.maxFrames === 36) saved.maxFrames = null;
  return { ...defaults(), ...saved };
}

function saveSettings(changes) {
  const next = { ...loadSettings(), ...changes };
  fs.mkdirSync(path.dirname(settingsFile()), { recursive: true });
  fs.writeFileSync(settingsFile(), JSON.stringify(next, null, 2));
  return next;
}

// ---------- locating programs ----------

function which(name) {
  try {
    const found = execFileSync('where.exe', [name], { encoding: 'utf8', windowsHide: true });
    return found.split(/\r?\n/).find(Boolean) || null;
  } catch {
    return null;
  }
}

// The frozen CLI shipped in the installer (resources/cli), with Python, ffmpeg and yt-dlp inside.
function bundledCli() {
  const file = path.join(process.resourcesPath, 'cli', 'video-agent.exe');
  return app.isPackaged && fs.existsSync(file) ? file : null;
}

// Settings first, then the bundled CLI, then one on PATH.
function cliCommand() {
  const custom = loadSettings().cli.trim();
  if (custom) return splitCommand(custom);
  if (bundledCli()) return [bundledCli()];
  return which('video-agent') ? ['video-agent'] : UVX_CLI;
}

// Child processes and terminals see the bundled CLI as `video-agent`, so agents and shells can run it too.
function childEnv(extra = {}) {
  const env = { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1', ...extra };
  if (bundledCli()) {
    // The copy is a plain object with Windows' own spelling (usually `Path`); adding `PATH` beside it would give the
    // child two entries, and node-pty's terminal would read the old one.
    const key = Object.keys(env).find((name) => name.toUpperCase() === 'PATH') || 'PATH';
    env[key] = `${path.dirname(bundledCli())};${env[key] || ''}`;
  }
  return env;
}

function splitCommand(text) {
  return (text.match(/"[^"]*"|\S+/g) || []).map((part) => part.replace(/^"|"$/g, ''));
}

// The folder that holds .claude-plugin/ and skills/: the repository in development, resources/plugin when packaged.
function pluginRoot() {
  return app.isPackaged ? path.join(process.resourcesPath, 'plugin') : path.resolve(__dirname, '..', '..');
}

function shells() {
  const found = [];
  const add = (id, label, file, args = []) => file && found.push({ id, label, file, args });
  add('pwsh', 'PowerShell 7', which('pwsh.exe'), ['-NoLogo']);
  add('powershell', 'Windows PowerShell', which('powershell.exe'), ['-NoLogo']);
  add('cmd', '命令提示符', which('cmd.exe'));
  const git = which('git.exe');
  const bash = [
    git && path.resolve(path.dirname(git), '..', 'bin', 'bash.exe'),
    'C:\\Program Files\\Git\\bin\\bash.exe',
  ].find((candidate) => candidate && fs.existsSync(candidate));
  add('gitbash', 'Git Bash', bash, ['--login', '-i']);
  return found;
}

// ---------- child processes ----------

function send(channel, value) {
  if (win && !win.isDestroyed()) win.webContents.send(channel, value);
}

// Programs are started directly when they resolve to an .exe, so arguments need no cmd.exe quoting. A .cmd or .bat
// shim needs cmd.exe; then arguments are quoted, and prompts always travel through stdin, never as arguments.
function launch(command, args) {
  const found = path.isAbsolute(command) ? command : which(command);
  if (found && /\.exe$/i.test(found)) return { file: found, args, shell: false };
  return { file: quote(found || command), args: args.map(quote), shell: true };
}

function startJob(id, command, args, { cwd, stdin, env, title = id, prompt, onClose } = {}) {
  const run = launch(command, args);
  const log = logs.job(id, { title, command: [command, ...args], cwd, ...(prompt ? { prompt } : {}) });
  const child = spawn(run.file, run.args, {
    cwd,
    shell: run.shell,
    windowsHide: true,
    env: childEnv(env),
    stdio: [stdin === undefined ? 'ignore' : 'pipe', 'pipe', 'pipe'],
  });
  jobs.set(id, { child, title });
  if (stdin !== undefined) child.stdin.end(stdin);
  const relay = (stream) => (chunk) => {
    const text = chunk.toString('utf8');
    log.write(text);
    queue.output(id, stream, text);
    send('job:output', { id, stream, text });
  };
  child.stdout.on('data', relay('stdout'));
  child.stderr.on('data', relay('stderr'));
  child.on('error', (error) => {
    log.write(`${error.message}\n`);
    queue.output(id, 'stderr', `${error.message}\n`);
    send('job:output', { id, stream: 'stderr', text: `${error.message}\n` });
  });
  child.on('close', (code) => {
    onClose?.();
    jobs.delete(id);
    log.close(code);
    queue.exited(id, code);
  });
}

function stopJob(id) {
  const job = jobs.get(id);
  if (job) spawn('taskkill', ['/PID', String(job.child.pid), '/T', '/F'], { windowsHide: true });
}

// ---------- tasks ----------

// Matches the window's check in app.js, which shows the login hint.
const isBilibili = (url) => /(^|[/.])(bilibili\.com|b23\.tv)([/:?#]|$)/i.test(url);

// The CLI arguments of each kind of task. The workspace is fixed when the task is added.
function cliArgs(task) {
  const out = ['-o', task.workspace];
  switch (task.kind) {
    case 'download':
      return ['download', task.url, '-o', path.join(task.workspace, '下载'), '--json'];
    case 'process': {
      const args = ['process', task.video, ...out, '--json', '--frame-interval', String(task.interval)];
      if (task.maxFrames) args.push('--max-frames', String(task.maxFrames));
      if (task.bcut) args.push('--asr', 'bcut', '--allow-remote-asr'); // consent given for this one task
      if (task.slides) args.push('--extract-slides');
      if (task.screenRegion) args.push('--screen-region', task.screenRegion);
      return args;
    }
    case 'frame':
      return ['frame', task.video, ...task.times, ...out];
    case 'summary': {
      const args = ['summarize', task.video, ...out];
      if (task.request) args.push('--request', task.request);
      if (task.overwrite) args.push('--overwrite');
      return args;
    }
    default:
      throw new Error(`unknown task kind: ${task.kind}`);
  }
}

function startTask(task) {
  if (task.kind === 'summary' && task.route !== 'api') return startAgent(task);
  const [command, ...prefix] = cliCommand();
  const args = [...prefix, ...cliArgs(task)];
  const options = { cwd: task.workspace, title: task.title };
  if (task.kind !== 'download' || !isBilibili(task.url)) return startJob(task.id, command, args, options);
  // The Bilibili login goes to yt-dlp as a cookies file that lives as long as the download.
  bilibili
    .writeCookies(path.join(cookiesDir(), `${task.id}.txt`))
    .then((cookies) => {
      if (task.stopping) return queue.exited(task.id, -1);
      startJob(task.id, command, [...args, ...(cookies ? ['--cookies', cookies] : [])], {
        ...options,
        onClose: () => cookies && fs.rmSync(cookies, { force: true }),
      });
    })
    .catch((error) => {
      queue.output(task.id, 'stderr', `${error.message}\n`);
      queue.exited(task.id, -1);
    });
}

// Agent route: Claude Code with the plugin, or Codex told to follow the skill file.
function startAgent(task) {
  const { agent, video, folder, request, overwrite, workspace, title } = task;
  const skill = path.join(pluginRoot(), 'skills', 'video-agent', 'SKILL.md');
  const text = [
    `总结这个视频：${video}`,
    `工作区是 ${workspace}，这个视频已经用 process 处理过，处理结果在 ${folder}。直接用这个文件夹，不要再运行 process，也不要上传音频。`,
    overwrite ? '已有的 总结.md 按要求重写。' : '',
    request ? `用户的要求：${request}` : '',
  ].filter(Boolean).join('\n');
  if (agent === 'claude') {
    const prompt = `用 video-agent skill 完成下面的任务。\n${text}`;
    startJob(task.id, 'claude', [
      '-p',
      '--plugin-dir', pluginRoot(),
      '--add-dir', workspace,
      '--permission-mode', 'acceptEdits',
      '--allowedTools', 'Bash(video-agent *)', 'Read', 'Write', 'Edit', 'Skill',
      '--output-format', 'stream-json', '--verbose',
    ], { cwd: workspace, stdin: prompt, title, prompt });
  } else {
    const prompt = `先读 ${skill} 并照它做，<video-agent> 用 video-agent 命令。\n${text}`;
    startJob(task.id, 'codex', [
      'exec', '--skip-git-repo-check', '--cd', workspace, '--sandbox', 'workspace-write', '--json', '-',
    ], { cwd: workspace, stdin: prompt, title, prompt });
  }
}

// "Process after download": the saved files are processed with the window's frame settings, without BCut (which
// needs consent per run) or slides; a video without subtitles is then processed again by hand if wanted.
function followUp(task) {
  if (task.kind !== 'download' || task.then !== 'process') return [];
  const { frameInterval, maxFrames } = loadSettings();
  return task.paths.map((video) => ({
    kind: 'process',
    title: `处理：${path.basename(video)}`,
    video,
    workspace: task.workspace,
    interval: frameInterval,
    maxFrames,
  }));
}

function createQueue() {
  queue = new TaskQueue({
    start: startTask,
    stop: (task) => stopJob(task.id),
    changed: () => {
      updateTray();
      send('tasks:changed', queue.list());
    },
    limits: () => ({ ...DEFAULT_LIMITS, ...loadSettings().limits }),
    followUp,
  });
}

// cmd.exe quoting for .cmd shims. cmd.exe still expands %NAME% inside quotes; such arguments are not supported.
function quote(value) {
  const text = String(value);
  if (/^[\w\-.:\\/=@+,]+$/.test(text)) return text;
  return `"${text.replace(/"/g, '""')}"`;
}

function runToEnd(command, args, stdin) {
  return new Promise((resolve) => {
    const run = launch(command, args);
    const child = spawn(run.file, run.args, {
      shell: run.shell,
      windowsHide: true,
      env: childEnv(),
    });
    child.stdin.end(stdin ?? '');
    let out = '';
    let err = '';
    child.stdout.on('data', (chunk) => (out += chunk.toString('utf8')));
    child.stderr.on('data', (chunk) => (err += chunk.toString('utf8')));
    child.on('error', (error) => resolve({ code: -1, out, err: error.message }));
    child.on('close', (code) => resolve({ code, out, err }));
  });
}

// ---------- Agent plugin ----------

// Install the Agent plugin from the local copy in the installer; no git or network needed. Both commands are
// idempotent, so the button also repairs or refreshes an earlier install.
async function installPlugin(agent) {
  const root = pluginRoot();
  const steps = agent === 'claude'
    ? [['claude', ['plugin', 'marketplace', 'add', root]], ['claude', ['plugin', 'marketplace', 'update', 'video-agent']],
       ['claude', ['plugin', 'install', 'video-agent@video-agent']]]
    : [['codex', ['plugin', 'marketplace', 'add', root]], ['codex', ['plugin', 'add', 'video-agent@video-agent']]];
  let output = '';
  for (const [command, args] of steps) {
    const { code, out, err } = await runToEnd(command, args);
    output += `$ ${command} ${args.join(' ')}\n${out}${err}\n`;
    if (code !== 0) {
      logs.line('warn', `plugin install for ${agent} failed at: ${command} ${args.join(' ')}`);
      return { ok: false, output };
    }
  }
  logs.line('info', `plugin installed for ${agent} from ${root}`);
  return { ok: true, output };
}

// After an update, bring the plugin in Claude Code and Codex up to the new version where it is installed. Claude Code
// loads it in place from the install folder but records the version; Codex keeps a copy per version.
async function refreshPluginsAfterUpdate() {
  const previous = loadSettings().lastVersion;
  saveSettings({ lastVersion: app.getVersion() });
  if (!previous || previous === app.getVersion()) return;
  const installed = {
    claude: (text) => text.includes('video-agent@video-agent'),
    codex: (text) => /^video-agent@video-agent\s+installed/m.test(text),
  };
  for (const agent of ['claude', 'codex']) {
    if (!which(agent)) continue;
    const { out } = await runToEnd(agent, ['plugin', 'list']);
    if (installed[agent](out)) {
      const { ok } = await installPlugin(agent);
      logs.line(ok ? 'info' : 'warn', `plugin refresh for ${agent} after ${previous} -> ${app.getVersion()}: ${ok ? 'done' : 'failed'}`);
    }
  }
}

function insideWorkspace(target) {
  const root = path.resolve(loadSettings().workspace).toLowerCase() + path.sep;
  return path.resolve(target).toLowerCase().startsWith(root);
}

// ---------- IPC ----------

function registerIpc() {
  ipcMain.handle('settings:get', () => loadSettings());
  ipcMain.handle('settings:set', (_, changes) => saveSettings(changes));
  ipcMain.handle('env:info', () => ({
    cli: cliCommand(),
    claude: which('claude'),
    codex: which('codex'),
    shells: shells().map(({ id, label }) => ({ id, label })),
    pluginRoot: pluginRoot(),
    bundled: !!bundledCli(),
  }));

  ipcMain.handle('plugin:install', (_, agent) => installPlugin(agent));

  ipcMain.handle('bilibili:status', () => bilibili.status());
  ipcMain.handle('bilibili:login', () => bilibili.login(win));
  ipcMain.handle('bilibili:logout', () => bilibili.logout());

  ipcMain.handle('update:state', () => updater.state());
  ipcMain.handle('update:check', () => updater.check());
  ipcMain.handle('update:download', () => updater.download());
  ipcMain.handle('update:install', (_, force) => updater.install(force));

  ipcMain.handle('dialog:videos', async () => {
    const result = await dialog.showOpenDialog(win, {
      title: '选择视频',
      properties: ['openFile', 'multiSelections'],
      filters: [
        { name: '视频', extensions: ['mp4', 'mkv', 'webm', 'mov', 'avi', 'flv', 'm4v', 'ts', 'wmv'] },
        { name: '所有文件', extensions: ['*'] },
      ],
    });
    return result.canceled ? [] : result.filePaths;
  });
  ipcMain.handle('dialog:file', async (_, { title, filters }) => {
    const result = await dialog.showOpenDialog(win, { title, properties: ['openFile'], filters });
    return result.canceled ? null : result.filePaths[0];
  });
  // Saves land in Downloads unless the user picks another folder.
  ipcMain.handle('dialog:save', async (_, { title, name }) => {
    const result = await dialog.showSaveDialog(win, {
      title,
      defaultPath: path.join(app.getPath('downloads'), name),
      filters: [{ name: 'zip', extensions: ['zip'] }],
    });
    return result.canceled ? null : result.filePath;
  });
  ipcMain.handle('dialog:folder', async (_, title) => {
    const result = await dialog.showOpenDialog(win, { title, properties: ['openDirectory', 'createDirectory'] });
    return result.canceled ? null : result.filePaths[0];
  });

  // Tasks (queued jobs) and one-shot CLI queries.
  ipcMain.handle('tasks:add', (_, spec) => queue.add({ ...spec, workspace: loadSettings().workspace }));
  ipcMain.handle('tasks:list', () => queue.list());
  ipcMain.handle('tasks:output', (_, id) => queue.get(id)?.output ?? []);
  ipcMain.handle('tasks:cancel', (_, id) => {
    logs.line('info', `task ${id} stopped by the user`);
    queue.cancel(id);
  });
  ipcMain.handle('tasks:retry', (_, id) => queue.retry(id));
  ipcMain.handle('tasks:clear', () => queue.clearFinished());
  ipcMain.handle('cli:json', async (_, args) => {
    const [command, ...prefix] = cliCommand();
    const { code, out, err } = await runToEnd(command, [...prefix, ...args]);
    if (code !== 0) return { error: (err || out).trim() || `exit ${code}` };
    try {
      return JSON.parse(out);
    } catch {
      return { error: `unexpected output: ${out.slice(0, 300)}` };
    }
  });
  ipcMain.handle('cli:text', (_, { args, stdin }) => {
    const [command, ...prefix] = cliCommand();
    return runToEnd(command, [...prefix, ...args], stdin);
  });
  // Files inside the workspace only.
  ipcMain.handle('fs:read', (_, file) => {
    if (!insideWorkspace(file)) throw new Error('只能读取工作区里的文件');
    return fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : null;
  });
  ipcMain.handle('shell:open', (_, target) => shell.openPath(target));
  ipcMain.handle('shell:reveal', (_, target) => shell.showItemInFolder(target));
  ipcMain.handle('shell:external', (_, url) => /^https?:\/\//.test(url) && shell.openExternal(url));
  ipcMain.handle('clipboard:write', (_, text) => clipboard.writeText(text));

  // Logs.
  ipcMain.handle('logs:list', () => logs.list());
  ipcMain.handle('logs:read', (_, file) => logs.read(file));
  ipcMain.handle('logs:open', () => shell.openPath(logs.dir));
  ipcMain.on('log:renderer', (_, message) => logs.line('error', `renderer: ${message}`));

  // Embedded terminal.
  ipcMain.handle('pty:start', (_, { id, shellId, cwd, cols, rows }) => {
    const choice = shells().find((item) => item.id === shellId) || shells()[0];
    const term = pty.spawn(choice.file, choice.args, {
      name: 'xterm-256color',
      cols,
      rows,
      cwd: cwd && fs.existsSync(cwd) ? cwd : loadSettings().workspace,
      env: childEnv(),
      useConpty: true,
    });
    terminals.set(id, term);
    logs.line('info', `terminal ${id} opened: ${choice.label} in ${cwd}`);
    term.onData((data) => send('pty:data', { id, data }));
    term.onExit(({ exitCode }) => {
      terminals.delete(id);
      send('pty:exit', { id, exitCode });
    });
    return choice.label;
  });
  ipcMain.on('pty:write', (_, { id, data }) => terminals.get(id)?.write(data));
  ipcMain.on('pty:resize', (_, { id, cols, rows }) => terminals.get(id)?.resize(cols, rows));
  ipcMain.handle('pty:kill', (_, id) => terminals.get(id)?.kill());
}

// ---------- window ----------

function createWindow() {
  win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 960,
    minHeight: 600,
    title: 'Video Agent',
    icon: path.join(ICONS, 'icon-256.png'),
    backgroundColor: nativeTheme.shouldUseDarkColors ? '#1b1a18' : '#faf9f7',
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, sandbox: true },
  });
  win.removeMenu();
  win.on('close', (event) => {
    if (quitting || !loadSettings().closeToTray || !tray) return;
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
    if (option('theme')) nativeTheme.themeSource = option('theme'); // light or dark
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

// ---------- tray ----------

function showWindow() {
  if (!win || win.isDestroyed()) return createWindow();
  if (win.isMinimized()) win.restore();
  win.show();
  win.focus();
}

function updateTray() {
  if (!tray) return;
  const running = queue.list().filter((task) => task.status === 'running').map((task) => task.title);
  const waiting = queue.list().filter((task) => task.status === 'queued').length;
  trayState.tooltip = running.length ? `Video Agent · 正在运行：${running.join('；')}` : 'Video Agent';
  tray.setToolTip(trayState.tooltip);
  tray.setContextMenu(
    (trayState.menu = Menu.buildFromTemplate([
      { label: '显示窗口', click: showWindow },
      { label: '添加本地视频…', click: () => (showWindow(), send('tray:add-videos')) },
      { type: 'separator' },
      { label: running.length ? `正在运行 ${running.length} 个任务${waiting ? `，排队 ${waiting} 个` : ''}` : '没有运行中的任务', enabled: false },
      { label: '停止所有任务', enabled: running.length + waiting > 0, click: () => queue.cancelAll() },
      { type: 'separator' },
      { label: '打开工作区', click: () => shell.openPath(loadSettings().workspace) },
      { label: '打开日志文件夹', click: () => shell.openPath(logs.dir) },
      { type: 'separator' },
      { label: '退出', click: () => app.quit() },
    ])),
  );
}

function createTray() {
  const image = nativeImage.createFromPath(path.join(ICONS, 'icon-16.png'));
  image.addRepresentation({ scaleFactor: 2, buffer: fs.readFileSync(path.join(ICONS, 'icon-32.png')) });
  tray = new Tray(image);
  tray.on('click', showWindow);
  updateTray();
}

// ---------- lifecycle ----------

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', showWindow);
  app.whenReady().then(() => {
    logs = new Logs(path.join(app.getPath('userData'), 'logs'));
    logs.line('info', `started ${app.getVersion()}, Electron ${process.versions.electron}`);
    process.on('uncaughtException', (error) => logs.line('error', error.stack || String(error)));
    fs.mkdirSync(loadSettings().workspace, { recursive: true });
    fs.rmSync(cookiesDir(), { recursive: true, force: true });
    createQueue();
    updater = createUpdater({ logs, send, settings: loadSettings, running: () => queue.active().length });
    registerIpc();
    createTray();
    createWindow();
    if (app.isPackaged) refreshPluginsAfterUpdate().catch((error) => logs.line('warn', `plugin refresh: ${error.message}`));
    // One quiet check a little after start; it only tells the window, it downloads nothing.
    if (loadSettings().checkUpdates !== false && (app.isPackaged || process.env.VA_UPDATE_ROOT)) {
      setTimeout(() => updater.check().catch(() => {}), Number(process.env.VA_UPDATE_DELAY_MS || 8000));
    }
  });
}

app.on('before-quit', () => (quitting = true));
app.on('will-quit', () => {
  queue?.cancelAll();
  for (const term of terminals.values()) term.kill();
  logs?.line('info', 'quit');
});
app.on('window-all-closed', () => app.quit());
