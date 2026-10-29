// The Agent plugin for Claude Code and Codex, and copies of the skill for agents without plugins.

const { app } = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const shared = require('./shared');
const { loadSettings, saveSettings } = require('./settings');
const { AGENTS, pluginRoot, runToEnd, which } = require('./programs');

// Install the Agent plugin from the local copy in the installer; no git or network needed. Both commands are
// idempotent, so the button also repairs or refreshes an earlier install.
async function installPlugin(agent) {
  const root = pluginRoot();
  /** @type {[string, string[]][]} */
  const steps = agent === 'claude'
    ? [['claude', ['plugin', 'marketplace', 'add', root]], ['claude', ['plugin', 'marketplace', 'update', 'video-agent']],
       ['claude', ['plugin', 'install', 'video-agent@video-agent']]]
    : [['codex', ['plugin', 'marketplace', 'add', root]], ['codex', ['plugin', 'add', 'video-agent@video-agent']]];
  let output = '';
  for (const [command, args] of steps) {
    const { code, out, err } = await runToEnd(command, args);
    output += `$ ${command} ${args.join(' ')}\n${out}${err}\n`;
    if (code !== 0) {
      shared.logs.line('warn', `plugin install for ${agent} failed at: ${command} ${args.join(' ')}`);
      return { ok: false, output };
    }
  }
  shared.logs.line('info', `plugin installed for ${agent} from ${root}`);
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
    shared.logs.line('warn', `skill copy to ${copy} failed: ${error.message}`);
    return { ok: false, output: `没有复制成功：${error.message}` };
  }
  saveSettings({ skillCopies: [...new Set([...(loadSettings().skillCopies || []), copy])] });
  shared.logs.line('info', `skill copied to ${copy}`);
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
      shared.logs.line(ok ? 'info' : 'warn', `plugin refresh for ${agent} after ${previous} -> ${app.getVersion()}: ${ok ? 'done' : 'failed'}`);
    }
  }
}

module.exports = { installPlugin, installSkill, refreshPluginsAfterUpdate };
