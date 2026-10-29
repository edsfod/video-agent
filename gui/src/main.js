// Electron main process: runs the Video Agent CLI, the Agent CLIs and terminal shells for the window.
// All media and summary work happens in the CLI; this file only starts processes and relays their output.

const { app, BrowserWindow, ipcMain, dialog, shell, clipboard, nativeTheme, Tray, Menu, nativeImage } = require('electron');

// 外观 in the settings (user request, 2026-10-28): follow Windows, or always light or dark.
const THEMES = ['system', 'light', 'dark'];
const { spawn, spawnSync, execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const pty = require('node-pty');
const { Logs } = require('./logs');
const { createUpdater } = require('./updater');
const accounts = require('./accounts');
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
global.vaAccounts = { writeCookies: (key, file) => accounts.writeCookies(key, file) };

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
    processAfterDownload: true, // downloaded files are processed, so their subtitles are imported at once
    // Compressing replaces the file (user decision, 2026-10-28): on for this program's downloads, off for videos added
    // from disk until the user agrees to have them replaced.
    compressDownloads: true,
    compressLocal: false,
    // A video without subtitles is transcribed with BCut, which uploads its audio to Bilibili: on unless the user turns
    // it off, also for videos processed after a download (user decision, 2026-10-28). The CLI still needs the flag.
    bcut: true,
    // Other agents shown as summary routes, [{ key, command }]: a key of AGENTS or 'custom', and its command line, where
    // {prompt} stands for the task if it takes no standard input. null shows the presets found on this computer.
    agents: null,
    webFiles: 50, // files a chat AI takes at once, for 导出文件夹 (DeepSeek's web chat: 50)
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
  // 0.8.2 and 0.8.3 kept one other agent, or none, as `agent` and `agentCommand`.
  if (!('agents' in saved) && 'agent' in saved) saved.agents = saved.agent ? [{ key: saved.agent, command: saved.agentCommand || '' }] : null;
  delete saved.agent;
  delete saved.agentCommand;
  return { ...defaults(), ...saved };
}

function saveSettings(changes) {
  const next = { ...loadSettings(), ...changes };
  fs.mkdirSync(path.dirname(settingsFile()), { recursive: true });
  fs.writeFileSync(settingsFile(), JSON.stringify(next, null, 2));
  return next;
}

// ---------- locating programs ----------

// An .exe first (started without a shell), then a .cmd or .bat; where.exe may list first a file with no extension that
// only Git Bash runs (pi's installer puts `pi` beside `pi.cmd`) or Hermes's `hermes.cmd` before its `hermes.exe`.
function which(name) {
  try {
    const found = execFileSync('where.exe', [name], { encoding: 'utf8', windowsHide: true }).split(/\r?\n/).filter(Boolean);
    return found.find((file) => /\.exe$/i.test(file)) || found.find((file) => /\.(cmd|bat|com)$/i.test(file)) || found[0] || null;
  } catch {
    return null;
  }
}

// The frozen CLI shipped in the installer (resources/cli), with Python, ffmpeg and yt-dlp inside.
function bundledCli() {
  const file = path.join(process.resourcesPath, 'cli', 'video-agent.exe');
  return app.isPackaged && fs.existsSync(file) ? file : null;
}

// In development, the CLI of this checkout (uv's editable install in .venv), so the window and the code it calls
// match; an installed Video Agent's CLI on PATH may be older. CI has no .venv and installs the checkout on PATH.
function sourceCli() {
  const file = path.resolve(__dirname, '..', '..', '.venv', 'Scripts', 'video-agent.exe');
  return !app.isPackaged && fs.existsSync(file) ? file : null;
}

// Settings first, then the bundled CLI (packaged) or this checkout's (development), then one on PATH.
function cliCommand() {
  const custom = loadSettings().cli.trim();
  if (custom) return splitCommand(custom);
  const own = bundledCli() || sourceCli();
  if (own) return [own];
  return which('video-agent') ? ['video-agent'] : UVX_CLI;
}

// Child processes and terminals see the app's own CLI as `video-agent`, so agents and shells can run it too.
function childEnv(extra = {}) {
  const env = { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1', ...extra };
  const own = bundledCli() || sourceCli();
  if (own) {
    // The copy is a plain object with Windows' own spelling (usually `Path`); adding `PATH` beside it would give the
    // child two entries, and node-pty's terminal would read the old one.
    const key = Object.keys(env).find((name) => name.toUpperCase() === 'PATH') || 'PATH';
    env[key] = `${path.dirname(own)};${env[key] || ''}`;
  }
  return env;
}

function splitCommand(text) {
  return (text.match(/"[^"]*"|\S+/g) || []).map((part) => part.replace(/^"|"$/g, ''));
}

// Agents besides Claude Code and Codex that run one task and exit (user request, 2026-10-28), with the commands their
// help gives for that (pi 0.99, Hermes Agent 0.21, DeepSeek Harness's README; dsh is in developer preview). Each reads
// the skill file as Codex does. None is limited to the workspace the way Codex's sandbox and Claude Code's allowed
// tools are: they run commands as the user. The user may edit the command in the settings.
// `installed`: where the program sits inside its desktop app, for one not on PATH: DeepSeek Harness's installer puts
// `dsh` there and adds nothing to PATH (user report, 2026-10-28, installed on D:).
// `model`: the option that names a model for one run (each agent's --help, 2026-10-29); DeepSeek Harness has none and
// takes a patch file instead (dshModel). `skills`: the folder it finds skills in without a plugin (its documentation,
// 2026-10-29): pi reads the Agent Skills folder ~/.agents/skills; Hermes Agent <HERMES_HOME>/skills, one category
// folder deep (its own skills sit in categories); DeepSeek Harness <dshHome>/skills (its skill-source table).
const AGENTS = {
  pi: { name: 'pi', command: 'pi -p', model: '--model', skills: () => path.join(os.homedir(), '.agents', 'skills') },
  hermes: {
    name: 'Hermes Agent',
    command: 'hermes chat --query-file - -Q',
    model: '-m',
    skills: () => path.join(process.env.HERMES_HOME || path.join(os.homedir(), '.hermes'), 'skills', 'media'),
  },
  dsh: {
    name: 'DeepSeek Harness',
    command: 'dsh --profile headless {prompt}',
    installed: { app: 'DeepSeek Harness', file: 'resources/runtime/cli/bin/dsh.cmd' },
    model: 'patch',
    skills: () => path.join(process.env.DSH_HOME || path.join(os.homedir(), '.dsh'), 'skills'),
  },
};

// The folders an app was installed to, from the uninstall entries Windows keeps (any drive), and the default ones.
function installFolders(app) {
  const folders = [];
  for (const hive of ['HKCU', 'HKLM']) {
    try {
      const key = `${hive}\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall`;
      // /f prints only the matching values (DisplayName), so each matching entry is read for its InstallLocation.
      const reg = (args) => execFileSync('reg.exe', ['query', ...args], { encoding: 'utf8', windowsHide: true });
      for (const entry of reg([key, '/s', '/f', app, '/d']).match(/^HKEY_\S.*$/gm) || []) {
        try {
          const location = /InstallLocation\s+REG_\w+\s+(.+?)\s*$/m.exec(reg([entry.trim(), '/v', 'InstallLocation']))?.[1];
          if (location) folders.push(location);
        } catch {
          // an entry without InstallLocation
        }
      }
    } catch {
      // no entry, or reg.exe found nothing
    }
  }
  for (const root of [process.env.LOCALAPPDATA && path.join(process.env.LOCALAPPDATA, 'Programs'), process.env.ProgramFiles]) {
    if (root) folders.push(path.join(root, app));
  }
  return folders;
}

// A preset's program: on PATH, or else inside its app's install folder.
function presetProgram(key) {
  const preset = AGENTS[key];
  const name = splitCommand(preset.command)[0];
  if (which(name) || !preset.installed) return name;
  const inside = installFolders(preset.installed.app).map((folder) => path.join(folder, preset.installed.file));
  return inside.find((file) => fs.existsSync(file)) || name;
}

const commandFound = (file) => (path.isAbsolute(file) ? fs.existsSync(file) : !!which(file));

// The other agents the summary routes offer, each with its command split and whether that command is here.
function otherAgents() {
  const { agents } = loadSettings();
  const chosen = agents ?? Object.keys(AGENTS).filter((key) => commandFound(presetProgram(key))).map((key) => ({ key }));
  return chosen.flatMap(({ key, command }) => {
    const line = (command || '').trim() || AGENTS[key]?.command || '';
    if (!line) return [];
    let [file, ...args] = splitCommand(line);
    if (AGENTS[key] && file === splitCommand(AGENTS[key].command)[0]) file = presetProgram(key); // as the preset names it
    const name = AGENTS[key]?.name || path.basename(file).replace(/\.(exe|cmd|bat)$/i, '');
    // A command of your own takes a model where it says {model}.
    const model = AGENTS[key]?.model || (args.includes('{model}') ? '{model}' : null);
    return [{ key, name, command: line, file, args, found: commandFound(file), model: !!model }];
  });
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


// The CLI arguments of each kind of task. The workspace is fixed when the task is added.
function cliArgs(task) {
  const out = ['-o', task.workspace];
  switch (task.kind) {
    case 'download': {
      // A followed list's new videos: the collection knows the list and the folder.
      if (task.update) return ['collection', 'update', task.update, ...out, '--json'];
      const args = ['download', task.url, '-o', path.join(task.workspace, '下载'), '--json'];
      if (task.playlist) args.push('--playlist');
      if (task.collection) args.push('--collection', task.collection, '--workspace', task.workspace);
      if (task.follow) args.push('--follow');
      if (task.auto) args.push('--auto');
      return args;
    }
    case 'process': {
      const args = ['process', task.video, ...out, '--json', '--frame-interval', String(task.interval)];
      if (task.maxFrames) args.push('--max-frames', String(task.maxFrames));
      if (task.bcut) args.push('--asr', 'bcut', '--allow-remote-asr'); // the user's BCut setting, on by default
      if (task.slides) args.push('--extract-slides');
      if (task.screenRegion) args.push('--screen-region', task.screenRegion);
      if (task.subtitles) args.push('--subtitles', task.subtitles);
      if (task.slidesFolder) args.push('--slides', task.slidesFolder);
      return args;
    }
    case 'frame':
      return ['frame', task.video, ...task.times, ...out];
    case 'compress':
      return ['compress', task.video, '--json'];
    case 'collection': {
      const args = ['summarize', '--collection', task.collection, ...out];
      if (task.model) args.push('--model', task.model);
      if (task.guide) args.push('--guide');
      if (task.request) args.push('--request', task.request);
      if (task.overwrite) args.push('--overwrite');
      return args;
    }
    case 'summary': {
      const args = ['summarize', task.video, ...out];
      if (task.model) args.push('--model', task.model);
      if (task.request) args.push('--request', task.request);
      if (task.overwrite) args.push('--overwrite');
      return args;
    }
    default:
      throw new Error(`unknown task kind: ${task.kind}`);
  }
}

// A compression stopped from here is killed before it can delete its half-written copy beside the video (named by
// files.temporary_beside); the next compression of that video would remove it too, but it may never come.
function removeLeftovers(video) {
  const { dir, name, ext } = path.parse(video);
  const escape = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const pattern = new RegExp(`^\\.${escape(name)}\\.[0-9a-f]{8}\\.part${escape(ext)}$`);
  try {
    for (const file of fs.readdirSync(dir).filter((item) => pattern.test(item))) fs.rmSync(path.join(dir, file), { force: true });
  } catch (error) {
    logs.line('warn', `could not remove what a stopped compression left beside ${video}: ${error.message}`);
  }
}

function startTask(task) {
  if (['summary', 'collection'].includes(task.kind) && task.route !== 'api') return startAgent(task);
  const [command, ...prefix] = cliCommand();
  const args = [...prefix, ...cliArgs(task)];
  const options = { cwd: task.workspace, title: task.title };
  // A second later: FFmpeg, killed with the tree, may hold the file a moment longer than the CLI.
  if (task.kind === 'compress') options.onClose = () => task.stopping && setTimeout(() => removeLeftovers(task.video), 1000);
  const site = task.kind === 'download' && accounts.siteOf(task.url);
  if (!site) return startJob(task.id, command, args, options);
  // The site's cookies go to yt-dlp as a cookies file that lives as long as the download.
  accounts
    .writeCookies(site, path.join(cookiesDir(), `${task.id}.txt`))
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

// Agent route: Claude Code with the plugin, or Codex or another agent told to follow the skill file.
function startAgent(task) {
  const { agent, video, folder, request, workspace, title } = task;
  const skill = path.join(pluginRoot(), 'skills', 'video-agent', 'SKILL.md');
  const file = task.guide ? '学习提纲.md' : '合集总结.md';
  const other = agent === 'claude' || agent === 'codex' ? null : otherAgents().find((entry) => entry.key === agent);
  if (agent !== 'claude' && agent !== 'codex' && !other) {
    queue.output(task.id, 'stderr', `设置里没有 ${agent} 这个 Agent。\n`);
    return queue.exited(task.id, -1);
  }
  const name = agent === 'claude' ? 'Claude Code' : agent === 'codex' ? 'Codex' : other.name;
  // An Agent writes files itself; keep the current text as a version first, so nothing is lost even if it overwrites.
  const [command, ...prefix] = cliCommand();
  const target = task.kind === 'collection'
    ? ['--collection', task.collection, ...(task.guide ? ['--guide'] : [])]
    : [video];
  spawnSync(command, [...prefix, 'versions', ...target, '-o', workspace, '--keep', name], { windowsHide: true, env: childEnv() });
  const save = (what, args) =>
    `写好后不要直接覆盖 ${what}：先写到一个临时文件，再运行 video-agent summarize ${args} -o "${workspace}" --import <临时文件> --source "${task.model ? `${name} ${task.model}` : name}" 保存（已经有 ${what} 时会另存为一个版本，由用户决定用哪个），然后删掉临时文件。`;
  const text = (task.kind === 'collection'
    ? [
        `为合集「${task.collection}」写 ${file}，按 skill 里「A collection」的做法。`,
        `工作区是 ${workspace}，合集文件夹是 ${folder}。先运行 video-agent collection show "${task.collection}" -o "${workspace}" 看各集的状态；还没有总结的视频先按 skill 写总结，几乎没有内容的视频用 collection skip 跳过并写明原因。不要上传音频。`,
        save(file, `--collection "${task.collection}"${task.guide ? ' --guide' : ''}`),
      ]
    : [
        `总结这个视频：${video}`,
        `工作区是 ${workspace}，这个视频已经用 process 处理过，处理结果在 ${folder}。直接用这个文件夹，不要再运行 process，也不要上传音频。`,
        save('总结.md', `"${video}"`),
      ]
  ).concat(request ? [`用户的要求：${request}`] : []).filter(Boolean).join('\n');
  if (agent === 'claude') {
    const prompt = `用 video-agent skill 完成下面的任务。\n${text}`;
    startJob(task.id, 'claude', [
      '-p',
      '--plugin-dir', pluginRoot(),
      '--add-dir', workspace,
      '--permission-mode', 'acceptEdits',
      '--allowedTools', 'Bash(video-agent *)', 'Read', 'Write', 'Edit', 'Skill',
      '--output-format', 'stream-json', '--verbose',
      ...(task.model ? ['--model', task.model] : []),
    ], { cwd: workspace, stdin: prompt, title, prompt });
  } else if (agent === 'codex') {
    const prompt = `先读 ${skill} 并照它做，<video-agent> 用 video-agent 命令。\n${text}`;
    startJob(task.id, 'codex', [
      'exec', '--skip-git-repo-check', '--cd', workspace, '--sandbox', 'workspace-write', '--json',
      ...(task.model ? ['-m', task.model] : []), '-',
    ], { cwd: workspace, stdin: prompt, title, prompt });
  } else {
    const prompt = `先读 ${skill} 并照它做，<video-agent> 用 video-agent 命令。\n${text}`;
    const temporary = [];
    const { args: modelArgs, file: patch, after } = agentModel(task, other);
    if (patch) temporary.push(patch);
    // Without a model, {model} goes, and the option before it too (as in `--model {model}`).
    let args = other.args.flatMap((arg, i, all) => {
      if (task.model) return [arg === '{model}' ? task.model : arg];
      return arg === '{model}' || (all[i + 1] === '{model}' && arg.startsWith('-')) ? [] : [arg];
    });
    const at = after && args.includes(after) ? args.indexOf(after) + 2 : args.length;
    args.splice(at, 0, ...modelArgs);
    const onClose = () => temporary.forEach((file) => fs.rmSync(file, { force: true }));
    if (!args.includes('{prompt}')) return startJob(task.id, other.file, args, { cwd: workspace, stdin: prompt, title, prompt, onClose });
    // A command line keeps one line through cmd.exe, so the task goes in a file and the line points to it.
    const taskFile = path.join(app.getPath('temp'), `video-agent-task-${task.id}.md`);
    fs.writeFileSync(taskFile, prompt);
    temporary.push(taskFile);
    args = args.map((arg) => (arg === '{prompt}' ? `读 ${taskFile} 并完成里面的任务。` : arg));
    startJob(task.id, other.file, args, { cwd: workspace, title, prompt, onClose });
  }
}

// The options that run another agent with the model chosen for this task (none: its own default). DeepSeek Harness
// takes a patch file for its agent-default-model entry, whose config is replaced whole, so the provider it has now
// is kept beside the new model.
function agentModel(task, other) {
  const how = AGENTS[other.key]?.model;
  if (!task.model || !how || how === '{model}') return { args: [] };
  if (how !== 'patch') return { args: [how, task.model] };
  const profile = other.args[other.args.indexOf('--profile') + 1] || 'headless';
  const run = launch(other.file, ['--profile', profile, '--dump-config']);
  const dump = spawnSync(run.file, run.args, { encoding: 'utf8', windowsHide: true, shell: run.shell, env: childEnv() });
  const provider = /dsh-agent-default-model'?\s+config:\s+provider:\s*(\S+)/.exec(dump.stdout || '')?.[1];
  if (!provider) {
    queue.output(task.id, 'stderr', `没读到 DeepSeek Harness 现在用的模型服务，用它的默认模型。\n`);
    return { args: [] };
  }
  const file = path.join(app.getPath('temp'), `video-agent-dsh-${task.id}.yml`);
  fs.writeFileSync(file, `- id: agent-default-model\n  config:\n    provider: ${provider}\n    model: ${JSON.stringify(task.model)}\n`);
  return { args: ['--patch', file], file, after: '--profile' }; // a launcher option: before the task, after the profile
}

// After a download: its new files are compressed when 压缩下载的视频 is on, then processed ("process after download")
// with the window's frame settings and BCut setting, without slides. Files the download found already saved, as when
// a collection of downloaded videos starts following its list, are left alone.
function followUp(task) {
  const { frameInterval, maxFrames, bcut, compressDownloads } = loadSettings();
  // Downloads are compressed first when the setting is on; processing follows the compression.
  if (task.kind === 'download' && compressDownloads !== false) {
    return (task.fresh || task.paths).map((video) => ({
      kind: 'compress', title: `压缩：${path.basename(video)}`, video, workspace: task.workspace, then: task.then,
    }));
  }
  const videos = task.kind === 'compress' ? [task.video] : task.kind === 'download' ? task.fresh || task.paths : [];
  if (task.then !== 'process') return [];
  return videos.map((video) => ({
    kind: 'process',
    title: `处理：${path.basename(video)}`,
    video,
    workspace: task.workspace,
    interval: task.interval ?? frameInterval,
    maxFrames: task.maxFrames ?? maxFrames,
    bcut: task.bcut ?? bcut, // a local video's answer in the window, else the BCut setting
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

// Agents without a plugin system get a copy of the skill folder where they look for skills (AGENTS[key].skills), or
// in a folder the user picks; a copy that is there again after an update is replaced by the new version.
function installSkill(target) {
  const parent = AGENTS[target]?.skills?.() || target;
  const copy = path.join(parent, 'video-agent');
  const source = path.join(pluginRoot(), 'skills', 'video-agent');
  // Only an earlier copy is replaced: a picked folder may hold some other video-agent folder, such as this project.
  if (fs.existsSync(copy) && !isSkillCopy(copy, source)) {
    return { ok: false, output: `${copy} 已经存在，而且不是之前复制的 skill，没有动它。请换一个文件夹，或者先自己移走它。` };
  }
  try {
    fs.rmSync(copy, { recursive: true, force: true });
    fs.mkdirSync(parent, { recursive: true });
    fs.cpSync(source, copy, { recursive: true });
  } catch (error) {
    logs.line('warn', `skill copy to ${copy} failed: ${error.message}`);
    return { ok: false, output: `没有复制成功：${error.message}` };
  }
  saveSettings({ skillCopies: [...new Set([...(loadSettings().skillCopies || []), copy])] });
  logs.line('info', `skill copied to ${copy}`);
  return { ok: true, output: `已复制到 ${copy}` };
}

function isSkillCopy(folder, source) {
  if ((loadSettings().skillCopies || []).includes(folder)) return true;
  try {
    const named = /^name:\s*video-agent\s*$/m.test(fs.readFileSync(path.join(folder, 'SKILL.md'), 'utf8'));
    const known = new Set(fs.readdirSync(source));
    return named && fs.readdirSync(folder).every((entry) => known.has(entry));
  } catch {
    return false;
  }
}

function refreshSkillCopies() {
  for (const copy of loadSettings().skillCopies || []) {
    if (fs.existsSync(path.join(copy, 'SKILL.md'))) installSkill(path.dirname(copy));
  }
}

// After an update, bring the plugin in Claude Code and Codex up to the new version where it is installed. Claude Code
// loads it in place from the install folder but records the version; Codex keeps a copy per version.
async function refreshPluginsAfterUpdate() {
  const previous = loadSettings().lastVersion;
  saveSettings({ lastVersion: app.getVersion() });
  if (!previous || previous === app.getVersion()) return;
  refreshSkillCopies();
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
  ipcMain.handle('skill:install', async (_, target) => {
    if (target !== 'folder') return installSkill(target);
    const picked = await dialog.showOpenDialog(win, { title: '选择 Agent 读 skill 的文件夹', properties: ['openDirectory', 'createDirectory'] });
    return picked.canceled ? null : installSkill(picked.filePaths[0]);
  });
  ipcMain.handle('skill:read', () => fs.readFileSync(path.join(pluginRoot(), 'skills', 'video-agent', 'SKILL.md'), 'utf8'));

  ipcMain.handle('accounts:list', () => accounts.list());
  ipcMain.handle('accounts:login', (_, key) => accounts.login(key, win));
  ipcMain.handle('accounts:logout', (_, key) => accounts.logout(key));
  ipcMain.handle('accounts:import', async (_, key) => {
    const picked = await dialog.showOpenDialog(win, {
      title: `导入${accounts.SITES[key].name}的 cookies.txt`,
      filters: [{ name: 'cookies.txt', extensions: ['txt'] }, { name: '所有文件', extensions: ['*'] }],
      properties: ['openFile'],
    });
    return picked.canceled ? null : accounts.importCookies(key, picked.filePaths[0]);
  });

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
  ipcMain.handle('tasks:cancel', (_, ids) => {
    for (const id of [ids].flat()) {
      logs.line('info', `task ${id} stopped by the user`);
      queue.cancel(id);
    }
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

// The GUI tests set this so their windows are never seen: off the screen, without a taskbar button, shown without
// taking the focus (user request, 2026-10-29: test windows took the focus, then still came up on top).
const BACKGROUND = !!process.env.VA_E2E_BACKGROUND;

function createWindow() {
  win = new BrowserWindow({
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
  win.removeMenu();
  if (BACKGROUND) win.showInactive();
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
  if (BACKGROUND) return win.showInactive();
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
    updater = createUpdater({ logs, send, settings: loadSettings, remember: saveSettings, running: () => queue.active().length });
    registerIpc();
    createTray();
    nativeTheme.themeSource = THEMES.includes(loadSettings().theme) ? loadSettings().theme : 'system';
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
