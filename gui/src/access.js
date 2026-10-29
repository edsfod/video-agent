// What the page may ask of the main process: which CLI commands it runs itself, and which paths it opens in their
// default program. Free of Electron, so the rules can be tested on their own (test/access.test.js).

const path = require('node:path');

const VIDEO_EXTENSIONS = ['mp4', 'mkv', 'webm', 'mov', 'avi', 'flv', 'm4v', 'ts', 'wmv'];

// The commands the page runs and reads at once. Downloads, processing, compressing and summaries with a model go
// through the task queue, whose command lines the main process builds.
const PAGE_COMMANDS = ['show', 'fix', 'versions', 'collection', 'config', 'template', 'tools', 'pack'];

function pageCommand(args) {
  if (!Array.isArray(args) || !args.length || !args.every((arg) => typeof arg === 'string')) return false;
  if (args[0] === 'compress') return args.includes('--check');
  if (args[0] === 'summarize') return args.includes('--import');
  if (args[0] === 'collection') return args[1] !== 'update';
  return PAGE_COMMANDS.includes(args[0]);
}

function inside(target, folder) {
  return path.resolve(target).toLowerCase().startsWith(path.resolve(folder).toLowerCase() + path.sep);
}

// Files and folders in the workspace, the CLI's settings folder (the summary templates), the licence files, and
// videos, since a summary links its source video, which may be anywhere. Not whatever path a link in a summary names:
// an imported summary is someone else's text. `places` gives the workspace, the CLI's settings folder and the files.
function openable(target, { workspace, cliSettings, files = [] }) {
  if (typeof target !== 'string' || !target.trim()) return false;
  const full = path.resolve(target);
  if (inside(full, workspace) || inside(full, cliSettings)) return true;
  if (files.some((file) => file && path.resolve(file).toLowerCase() === full.toLowerCase())) return true;
  return VIDEO_EXTENSIONS.includes(path.extname(full).slice(1).toLowerCase());
}

module.exports = { VIDEO_EXTENSIONS, inside, openable, pageCommand };
