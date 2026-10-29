// The settings dialog.

import { $, $$, element, failed, LIMITED, state } from './state.js';
import { ACTIVE } from './task-panel.js';
import { renderRules } from './templates.js';
import { renderUpdate } from './updates.js';

$('open-settings').onclick = async () => {
  $('set-workspace').value = state.settings.workspace;
  $('set-cli').value = state.settings.cli;
  renderAgentRows();
  $('set-key').value = '';
  $('set-close-to-tray').checked = state.settings.closeToTray !== false;
  $('set-compress-downloads').checked = state.settings.compressDownloads !== false;
  $('set-compress-local').checked = state.settings.compressLocal === true;
  $('set-theme').value = state.settings.theme || 'system';
  $('set-check-updates').checked = state.settings.checkUpdates !== false;
  $('set-beta-updates').checked = state.settings.betaUpdates ?? (state.appVersion || '').includes('-'); // as updater.js decides
  for (const kind of LIMITED) $(`set-limit-${kind}`).value = state.settings.limits[kind] ?? 1;
  renderWorkspaceLock();
  $('set-update-mirror').value = state.settings.updateMirror || '';
  renderUpdate(await window.va.updateState());
  renderRules();
  const cli = state.env.bundled ? '安装程序自带的 video-agent' : state.env.cli.join(' ');
  $('env-info').textContent =
    `正在用的命令：${cli} · Claude Code：${state.env.claude ? '已找到' : '没有找到'} · Codex：${state.env.codex ? '已找到' : '没有找到'}` +
    state.env.others.map((agent) => ` · ${agent.name}：${agent.found ? '已找到' : '没有找到'}`).join('');
  renderExtractor();
  $('install-claude').disabled = !state.env.claude;
  $('install-codex').disabled = !state.env.codex;
  $('plugin-output').hidden = true;
  const config = await window.va.cliJson(['config', '--json']);
  if (failed(config)) {
    $('api-info').textContent = `读取不到 API 设置：${config.error}`;
  } else {
    $('set-provider').value = config.provider;
    $('set-model').value = config.model || '';
    $('set-base-url').value = config.base_url || '';
    $('api-info').textContent = `API key：${config.key || '还没有'}`;
  }
  $('settings-unsaved').hidden = true;
  $('settings').showModal();
  settingsShown = settingsValues();
};

// Closing by ×, Esc or a click outside keeps nothing; with changes it asks first, otherwise it just closes.
let settingsShown = '';
const SETTINGS_FIELDS = [
  'set-theme', 'set-workspace', 'set-cli', 'set-close-to-tray', 'set-compress-downloads', 'set-compress-local', 'set-check-updates', 'set-beta-updates', 'set-update-mirror', 'set-limit-download',
  'set-limit-process', 'set-limit-summary', 'set-limit-compress', 'set-provider', 'set-model', 'set-base-url', 'set-key',
];
const settingsValues = () =>
  JSON.stringify([SETTINGS_FIELDS.map((id) => ($(id).type === 'checkbox' ? $(id).checked : $(id).value)), agentRowsValue()]);
// AutoSlides Extractor: where the CLI finds it, and the portable build downloaded on request (extractor.js).
function renderExtractor() {
  const found = state.tools?.slide_extractor;
  $('extractor-info').textContent = found ? `正在用：${found}` : '没有找到，屏幕页用本程序自己的规则。';
  $('download-extractor').textContent = found ? '下载最新的免安装版' : '下载免安装版';
}

$('download-extractor').onclick = async () => {
  const button = /** @type {HTMLButtonElement} */ ($('download-extractor'));
  button.disabled = true;
  $('extractor-info').textContent = '正在查最新版本…';
  const off = window.va.onExtractorProgress(({ source, received, total }) => {
    $('extractor-info').textContent = `从 ${source} 下载：${(received / 1048576).toFixed(1)} / ${(total / 1048576).toFixed(0)} MB`;
  });
  try {
    const { version } = await window.va.downloadExtractor();
    const found = await window.va.cliJson(['tools', '--json']);
    if (!failed(found)) state.tools = found;
    renderExtractor();
    $('extractor-info').textContent = `已下载 ${version}。${$('extractor-info').textContent}`;
  } catch (error) {
    $('extractor-info').textContent = `没有下载成功：${String(error.message).replace(/^Error invoking remote method '[^']+': (Error: )?/, '')}`;
  } finally {
    off();
    button.disabled = false;
  }
};

function closeSettings() {
  if (settingsValues() === settingsShown) return $('settings').close('cancel');
  $('settings-unsaved').hidden = false;
  $('discard-settings').textContent = '不保存';
  $('save-settings').focus();
}
$('close-settings').onclick = closeSettings;
$('settings').addEventListener('cancel', (event) => (event.preventDefault(), closeSettings()));
$('settings').addEventListener('click', (event) => event.target === $('settings') && closeSettings());
$('set-theme').onchange = () => window.va.previewTheme($('set-theme').value);
// One row per preset and one for a command of the user's own: ticked ones become summary routes. A preset's box holds
// its command to edit; until the settings were saved with these rows, the presets found here are the ticked ones.
export let agentRowsShown = '';
function renderAgentRows() {
  const saved = Object.fromEntries(state.env.others.map((agent) => [agent.key, agent.command]));
  /** @type {[string, import('../va').Preset][]} */
  const presets = [...Object.entries(state.env.agents), ['custom', { name: '自定义命令', command: '' }]];
  const rows = presets.map(([key, preset]) => {
    const on = element('input', { type: 'checkbox', checked: key in saved });
    const command = element('input', {
      type: 'text', spellcheck: false, value: saved[key] || preset.command, placeholder: '例如 my-agent run --print', disabled: !on.checked,
    });
    on.dataset.agent = key;
    command.dataset.agentCommand = key;
    on.onchange = () => (command.disabled = !on.checked);
    const found = 'found' in preset ? (preset.found ? '（已找到）' : '（没有找到）') : '';
    const label = element('label', { className: 'check inline' }, [on, element('span', { textContent: preset.name + found })]);
    return element('div', { className: 'row agent-row' }, [label, command]);
  });
  $('set-agents').replaceChildren(...rows);
  agentRowsShown = JSON.stringify(agentRowsValue());
}
export const agentRowsValue = () =>
  [...$$('#set-agents input[data-agent]')].filter((box) => box.checked).map((box) => {
    const command = /** @type {HTMLInputElement} */ (document.querySelector(`#set-agents input[data-agent-command="${box.dataset.agent}"]`)).value.trim();
    return { key: box.dataset.agent, command: command === state.env.agents[box.dataset.agent]?.command ? '' : command };
  });
$('settings').addEventListener('close', () => {
  // Setting the theme repaints the whole window (most of a second), so only a previewed one is put back.
  const saved = state.settings.theme || 'system';
  if ($('settings').returnValue !== 'save' && $('set-theme').value !== saved) window.va.previewTheme(saved);
  $('settings-unsaved').hidden = true;
  $('discard-settings').textContent = '取消';
});
// Read-only windows close on a click outside too.
for (const id of ['skill-dialog', 'privacy-dialog', 'logs']) $(id).addEventListener('click', (event) => event.target === $(id) && $(id).close());

for (const agent of ['claude', 'codex']) {
  $(`install-${agent}`).onclick = async () => {
    const name = agent === 'claude' ? 'Claude Code' : 'Codex';
    const box = $('plugin-output');
    box.hidden = false;
    box.textContent = `正在安装到 ${name}…`;
    const result = await window.va.installPlugin(agent);
    box.textContent = `${result.ok ? `已装好。重新打开 ${name} 后生效。` : '没有装好，输出如下：'}\n\n${result.output}`;
  };
}

// Agents without plugins: the skill folder is copied where each reads skills (shown on hover), or into a picked folder.
for (const button of $$('#skill-targets button')) {
  const target = button.dataset.skill;
  button.onclick = async () => {
    const result = await window.va.installSkill(target);
    if (!result) return; // no folder picked
    const box = $('plugin-output');
    box.hidden = false;
    const name = state.env.agents[target]?.name || 'Agent';
    box.textContent = result.ok ? `${result.output}。${name} 下次启动时读到它。` : result.output;
  };
}

// Tasks keep the workspace they were added with; changing it under them would hide their results.
export function renderWorkspaceLock() {
  const active = state.tasks.filter((task) => ACTIVE.has(task.status)).length;
  $('pick-workspace').disabled = active > 0;
  $('workspace-lock').hidden = active === 0;
}
