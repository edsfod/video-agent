// What the page can ask for (preload.js, va.d.ts): every ipcMain handler.

const { ipcMain, nativeTheme, dialog, app, shell, clipboard } = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const pty = require('node-pty');
const shared = require('./shared');
const { send } = shared;
const models = require('./models');
const accounts = require('./accounts');
const { THEMES, cookiesDir, loadSettings, saveSettings } = require('./settings');
const { AGENTS, VERSION, aboutFiles, bundledCli, childEnv, cliCommand, commandFound, otherAgents, pluginRoot, presetProgram, runToEnd, shells, which } = require('./programs');
const { installPlugin, installSkill } = require('./plugins');

function insideWorkspace(target) {
  const root = path.resolve(loadSettings().workspace).toLowerCase() + path.sep;
  return path.resolve(target).toLowerCase().startsWith(root);
}

// The window that asked, for a dialog's parent: the page asks only while the window is there.
const parent = () => /** @type {Electron.BrowserWindow} */ (shared.win);

function registerIpc() {
  ipcMain.handle('settings:get', () => loadSettings());
  ipcMain.handle('settings:set', (_, changes) => {
    if (changes.theme) nativeTheme.themeSource = changes.theme;
    return saveSettings(changes);
  });
  // The settings preview a theme before it is saved; closing them without saving sets the saved one again.
  ipcMain.handle('theme:preview', (_, theme) => (nativeTheme.themeSource = THEMES.includes(theme) ? theme : 'system'));
  ipcMain.handle('env:info', () => ({
    cli: cliCommand(),
    claude: which('claude'),
    codex: which('codex'),
    others: otherAgents(),
    agents: Object.fromEntries(
      Object.entries(AGENTS).map(([key, { name, command, skills }]) => [
        key, { name, command, found: commandFound(presetProgram(key)), skills: skills() },
      ]),
    ),
    shells: shells().map(({ id, label }) => ({ id, label })),
    pluginRoot: pluginRoot(),
    bundled: !!bundledCli(),
  }));

  ipcMain.handle('plugin:install', (_, agent) => installPlugin(agent));
  ipcMain.handle('models:list', (_, route) => {
    const [command, ...prefix] = cliCommand();
    return models.list(route, {
      other: otherAgents().find((entry) => entry.key === route),
      run: (file, args) => runToEnd(file, args),
      cli: (args) => runToEnd(command, [...prefix, ...args]),
    });
  });
  ipcMain.handle('skill:install', async (_, target) => {
    if (target !== 'folder') return installSkill(target);
    const picked = await dialog.showOpenDialog(parent(), { title: '选择 Agent 读 skill 的文件夹', properties: ['openDirectory', 'createDirectory'] });
    return picked.canceled ? null : installSkill(picked.filePaths[0]);
  });
  ipcMain.handle('skill:read', () => fs.readFileSync(path.join(pluginRoot(), 'skills', 'video-agent', 'SKILL.md'), 'utf8'));
  ipcMain.handle('about:info', () => {
    const files = aboutFiles();
    return { version: VERSION, ...files, privacy: fs.readFileSync(files.privacy, 'utf8') };
  });

  ipcMain.handle('accounts:list', () => accounts.list());
  ipcMain.handle('accounts:login', (_, key) => accounts.login(key));
  ipcMain.handle('accounts:browsers', () => accounts.browsers());
  // yt-dlp reads the browser's cookies (--cookies-from-browser) and writes them to a file the site's are taken from;
  // the page it is pointed at only gives it something to do, nothing is downloaded.
  ipcMain.handle('accounts:from-browser', async (_, key, browser) => {
    const [command, ...prefix] = cliCommand();
    const tools = await runToEnd(command, [...prefix, 'tools', '--json']);
    let ytdlp = null;
    try {
      ytdlp = JSON.parse(tools.out).yt_dlp;
    } catch {
      // reported below
    }
    if (!ytdlp) return { error: '没找到 yt-dlp，读不了浏览器的 Cookie。' };
    const file = path.join(cookiesDir(), `from-${browser}-${Date.now()}.txt`);
    fs.mkdirSync(cookiesDir(), { recursive: true });
    try {
      const { err } = await runToEnd(ytdlp, [
        '--cookies-from-browser', browser, '--cookies', file,
        '--skip-download', '--simulate', '--no-warnings', '--playlist-items', '0', accounts.SITES[key].home,
      ]);
      if (!fs.existsSync(file) || /ERROR:.*cookie|decrypt/i.test(err)) return { error: accounts.browserError(browser, err) };
      return await accounts.importCookies(key, file);
    } finally {
      fs.rmSync(file, { force: true });
    }
  });
  ipcMain.handle('accounts:logout', (_, key) => accounts.logout(key));
  ipcMain.handle('accounts:import', async (_, key) => {
    const picked = await dialog.showOpenDialog(parent(), {
      title: `导入${accounts.SITES[key].name}的 cookies.txt`,
      filters: [{ name: 'cookies.txt', extensions: ['txt'] }, { name: '所有文件', extensions: ['*'] }],
      properties: ['openFile'],
    });
    return picked.canceled ? null : accounts.importCookies(key, picked.filePaths[0]);
  });

  ipcMain.handle('update:state', () => shared.updater.state());
  ipcMain.handle('update:check', () => shared.updater.check());
  ipcMain.handle('update:download', () => shared.updater.download());
  ipcMain.handle('update:install', (_, force) => shared.updater.install(force));

  ipcMain.handle('dialog:videos', async () => {
    const result = await dialog.showOpenDialog(parent(), {
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
    const result = await dialog.showOpenDialog(parent(), { title, properties: ['openFile'], filters });
    return result.canceled ? null : result.filePaths[0];
  });
  // Saves land in Downloads unless the user picks another folder.
  ipcMain.handle('dialog:save', async (_, { title, name }) => {
    const result = await dialog.showSaveDialog(parent(), {
      title,
      defaultPath: path.join(app.getPath('downloads'), name),
      filters: [{ name: 'zip', extensions: ['zip'] }],
    });
    return result.canceled ? null : result.filePath;
  });
  ipcMain.handle('dialog:folder', async (_, title) => {
    const result = await dialog.showOpenDialog(parent(), { title, properties: ['openDirectory', 'createDirectory'] });
    return result.canceled ? null : result.filePaths[0];
  });

  // Tasks (queued jobs) and one-shot CLI queries.
  ipcMain.handle('tasks:add', (_, spec) => shared.queue.add({ ...spec, workspace: loadSettings().workspace }));
  ipcMain.handle('tasks:list', () => shared.queue.list());
  ipcMain.handle('tasks:output', (_, id) => shared.queue.get(id)?.output ?? []);
  ipcMain.handle('tasks:cancel', (_, ids) => {
    for (const id of [ids].flat()) {
      shared.logs.line('info', `task ${id} stopped by the user`);
      shared.queue.cancel(id);
    }
  });
  ipcMain.handle('tasks:retry', (_, id) => shared.queue.retry(id));
  ipcMain.handle('tasks:clear', () => shared.queue.clearFinished());
  ipcMain.handle('cli:json', async (_, args) => {
    const [command, ...prefix] = cliCommand();
    const { code, out, err } = await runToEnd(command, [...prefix, ...args]);
    // Logged, so a list that failed to show can be traced (the window only shows the last line).
    const failed = (error) => (shared.logs.line('warn', `cli ${args.slice(0, 2).join(' ')} failed: ${error.slice(0, 500)}`), { error });
    if (code !== 0) return failed((err || out).trim() || `exit ${code}`);
    try {
      return JSON.parse(out);
    } catch {
      return failed(`unexpected output: ${out.slice(0, 300)}${err ? ` / ${err.trim().slice(0, 200)}` : ''}`);
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
  ipcMain.handle('logs:list', () => shared.logs.list());
  ipcMain.handle('logs:read', (_, file) => shared.logs.read(file));
  ipcMain.handle('logs:open', () => shell.openPath(shared.logs.dir));
  ipcMain.on('log:renderer', (_, message) => shared.logs.line('error', `renderer: ${message}`));

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
    shared.terminals.set(id, term);
    shared.logs.line('info', `terminal ${id} opened: ${choice.label} in ${cwd}`);
    term.onData((data) => send('pty:data', { id, data }));
    term.onExit(({ exitCode }) => {
      shared.terminals.delete(id);
      send('pty:exit', { id, exitCode });
    });
    return choice.label;
  });
  ipcMain.on('pty:write', (_, { id, data }) => shared.terminals.get(id)?.write(data));
  ipcMain.on('pty:resize', (_, { id, cols, rows }) => shared.terminals.get(id)?.resize(cols, rows));
  ipcMain.handle('pty:kill', (_, id) => shared.terminals.get(id)?.kill());
}

module.exports = { registerIpc };
