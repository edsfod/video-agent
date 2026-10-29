// Finding and running programs: the Video Agent CLI (the bundled one, this checkout's, or one on PATH), Claude Code,
// Codex and the other agents, the shells for the terminal, the plugin and licence files.

const { app } = require('electron');
const { execFileSync, spawn } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
const os = require('node:os');
const { loadSettings } = require('./settings');

const VERSION = app.getVersion(); // package.json, kept equal to the CLI version
// Last resort in development when no CLI is installed: the release wheel through uvx (needs uv, not git).
const UVX_CLI = [
  'uvx', '--from',
  `https://github.com/edsfod/video-agent/releases/download/v${VERSION}/video_agent-${VERSION}-py3-none-any.whl`,
  'video-agent',
];

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
  /** @type {Record<string, string | undefined>} */
  const env = { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1', ...extra };
  // AutoSlides Extractor downloaded from the settings, unless the user's own AUTOSLIDES_EXTRACTOR says otherwise.
  const extractor = !env.AUTOSLIDES_EXTRACTOR && require('./extractor').downloaded();
  if (extractor) env.AUTOSLIDES_EXTRACTOR = extractor;
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

// PRIVACY.md, the licence and the third-party notices: where the installer puts them, or in the source tree (where
// the notices exist only after a CLI build).
function aboutFiles() {
  const root = path.resolve(__dirname, '..', '..');
  const found = (file) => (fs.existsSync(file) ? file : null);
  if (!app.isPackaged) {
    const notices = path.join(root, 'build', 'cli', 'video-agent', 'THIRD-PARTY-NOTICES.txt');
    return { privacy: path.join(root, 'PRIVACY.md'), license: found(path.join(root, 'LICENSE')), notices: found(notices) };
  }
  return {
    privacy: path.join(process.resourcesPath, 'PRIVACY.md'),
    license: found(path.join(process.resourcesPath, 'LICENSE.txt')),
    notices: found(path.join(path.dirname(process.execPath), 'THIRD-PARTY-NOTICES.txt')),
  };
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

// Programs are started directly when they resolve to an .exe, so arguments need no cmd.exe quoting. A .cmd or .bat
// shim needs cmd.exe; then arguments are quoted, and prompts always travel through stdin, never as arguments.
function launch(command, args) {
  const found = path.isAbsolute(command) ? command : which(command);
  if (found && /\.exe$/i.test(found)) return { file: found, args, shell: false };
  return { file: quote(found || command), args: args.map(quote), shell: true };
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

module.exports = { AGENTS, VERSION, aboutFiles, bundledCli, childEnv, cliCommand, commandFound, launch, otherAgents, pluginRoot, presetProgram, runToEnd, shells, which };
