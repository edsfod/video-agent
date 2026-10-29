// The models and thinking levels each summary route offers on the summary page (user request, 2026-10-29: a full
// list, read without spending tokens, and the thinking level too). Each comes from what the agent keeps or prints
// itself, looked up that day:
//   Claude Code: no command lists models; its --help names the aliases and --effort low|medium|high|xhigh|max.
//   Codex: ~/.codex/models_cache.json, the catalog the app downloads, with each model's reasoning levels
//     (-c model_reasoning_effort=…).
//   pi: `pi --list-models` (provider and model per line); --thinking off|minimal|low|medium|high|xhigh|max.
//   Hermes Agent: <HERMES_HOME>/provider_models_cache.json for the provider its config.yaml names;
//     --reasoning none|minimal|low|medium|high|xhigh|max|ultra.
//   DeepSeek Harness: the models its profiles list (--dump-config, and the desktop profile's own patch); no thinking
//     option.
//   Model API: `video-agent models`, the provider's model list (a GET, no tokens); summarize --effort low|medium|high.
// A list that cannot be read is empty; the page then offers the route's default and a model typed in.

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const CLAUDE_EFFORTS = ['low', 'medium', 'high', 'xhigh', 'max'];
const PI_THINKING = ['off', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max'];
const HERMES_REASONING = ['none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max', 'ultra'];
const API_EFFORTS = ['low', 'medium', 'high'];

// Claude Code's aliases follow the newest model of each family; full names pick one exactly.
const CLAUDE_MODELS = [
  { value: 'opus', label: 'opus（最新的 Opus）' },
  { value: 'sonnet', label: 'sonnet（最新的 Sonnet）' },
  { value: 'haiku', label: 'haiku（最新的 Haiku）' },
  { value: 'claude-opus-5-5', label: 'claude-opus-5-5' },
  { value: 'claude-sonnet-5-5', label: 'claude-sonnet-5-5' },
  { value: 'claude-haiku-5-5', label: 'claude-haiku-5-5' },
  { value: 'claude-fable-5-1', label: 'claude-fable-5-1' },
];

const readJson = (file) => {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch {
    return null;
  }
};

function codex() {
  const cache = readJson(path.join(process.env.CODEX_HOME || path.join(os.homedir(), '.codex'), 'models_cache.json'));
  const listed = (cache?.models || []).filter((model) => model.slug && model.visibility !== 'hide');
  const levels = new Set(listed.flatMap((model) => (model.supported_reasoning_levels || []).map((level) => level.effort)));
  return {
    models: listed.map((model) => ({
      value: model.slug,
      label: model.display_name && model.display_name !== model.slug ? `${model.display_name}（${model.slug}）` : model.slug,
      efforts: (model.supported_reasoning_levels || []).map((level) => level.effort),
    })),
    efforts: [...levels],
  };
}

// `pi --list-models` prints a table: provider, model, then sizes and abilities.
function piModels(text) {
  return text
    .split('\n')
    .slice(1)
    .map((line) => line.trim().split(/\s+/))
    .filter((cells) => cells.length >= 2 && cells[0] && cells[1])
    .map(([provider, model]) => ({ value: `${provider}/${model}`, label: `${model}（${provider}）` }));
}

function hermes() {
  const home = process.env.HERMES_HOME || path.join(os.homedir(), '.hermes');
  let provider = null;
  try {
    // config.yaml: `model:` then, indented under it, `provider: "…"`; the block ends at the next unindented line.
    const lines = fs.readFileSync(path.join(home, 'config.yaml'), 'utf8').split(/\r?\n/);
    const start = lines.findIndex((line) => /^model:\s*$/.test(line));
    for (const line of start < 0 ? [] : lines.slice(start + 1)) {
      if (/^\S/.test(line)) break;
      const found = /^\s+provider:\s*["']?([^"'\s#]+)/.exec(line);
      if (found) {
        provider = found[1];
        break;
      }
    }
  } catch {
    // no config
  }
  const cache = readJson(path.join(home, 'provider_models_cache.json')) || {};
  const models = (provider && cache[provider]?.models) || [];
  return { models: models.map((model) => ({ value: model, label: model })), efforts: HERMES_REASONING, provider };
}

// DeepSeek Harness: model ids in its profiles' configs (`models: - id: …`) and the model it uses now.
function dshModels(dump) {
  const ids = new Set();
  const current = /dsh-agent-default-model'?\s+config:\s+provider:\s*\S+\s+model:\s*(\S+)/.exec(dump)?.[1];
  if (current) ids.add(current);
  const home = process.env.DSH_HOME || path.join(os.homedir(), '.dsh');
  const texts = [dump];
  try {
    for (const profile of fs.readdirSync(path.join(home, 'profiles'))) {
      const patch = path.join(home, 'profiles', profile, 'cordis.patch.yml');
      if (fs.existsSync(patch)) texts.push(fs.readFileSync(patch, 'utf8'));
    }
  } catch {
    // no profiles
  }
  for (const text of texts) {
    for (const block of text.matchAll(/^\s*models:\n((?:\s+.*\n)*)/gm)) {
      for (const id of block[1].matchAll(/^\s*- id:\s*(\S+)/gm)) ids.add(id[1]);
    }
  }
  return [...ids].map((id) => ({ value: id, label: id === current ? `${id}（现在用的）` : id }));
}

// route: claude, codex, api, or another agent's key; other: its otherAgents() entry; run(command, args): output.
async function list(route, { other, run, cli }) {
  if (route === 'claude') return { models: CLAUDE_MODELS, efforts: CLAUDE_EFFORTS };
  if (route === 'codex') return codex();
  if (route === 'api') {
    const { code, out, err } = await cli(['models', '--json']);
    if (code !== 0) return { models: [], efforts: API_EFFORTS, error: (err || out).trim().split('\n').pop() };
    try {
      return { models: JSON.parse(out).map((id) => ({ value: id, label: id })), efforts: API_EFFORTS };
    } catch {
      return { models: [], efforts: API_EFFORTS };
    }
  }
  if (!other) return { models: [], efforts: [] };
  if (route === 'pi') {
    const { out } = await run(other.file, ['--list-models']);
    return { models: piModels(out || ''), efforts: PI_THINKING };
  }
  if (route === 'hermes') return hermes();
  if (route === 'dsh') {
    const profile = other.args[other.args.indexOf('--profile') + 1] || 'headless';
    const { out } = await run(other.file, ['--profile', profile, '--dump-config']);
    return { models: dshModels(out || ''), efforts: [] };
  }
  return { models: [], efforts: [] }; // a command of one's own: a model typed in, where it says {model}
}

// The options that give an agent the thinking level chosen (none for DeepSeek Harness and commands of one's own).
function effortArgs(route, effort) {
  if (!effort) return [];
  return {
    claude: ['--effort', effort],
    codex: ['-c', `model_reasoning_effort="${effort}"`],
    pi: ['--thinking', effort],
    hermes: ['--reasoning', effort],
  }[route] || [];
}

module.exports = { list, effortArgs, piModels, dshModels };
