// Summary templates: the summary page's choice and 设置 → 总结模板, and 设置 → 关于.

import { agentRowsShown, agentRowsValue } from './settings.js';
import { $, element, failed, LIMITED, markdown, state } from './state.js';
import { SOURCE_PAGE } from './updates.js';
import { refresh } from './video-list.js';
import { renderVideo } from './video-view.js';

// Several summary templates exist side by side (user request, 2026-10-29). The one chosen on the summary page is the
// CLI's chosen template, so an Agent run from a terminal follows it too; each task keeps the one it was added with.

export const STANDARD_TEMPLATE = '标准';
export const chosenTemplate = () => state.templates.find((entry) => entry.current)?.name || STANDARD_TEMPLATE;
const templateLabel = (entry) => (!entry.builtin ? `${entry.name}（自己的）` : entry.customized ? `${entry.name}（改过）` : entry.name);

export async function loadTemplates() {
  const list = await window.va.cliJson(['template', '--list']);
  $('route-template-note').textContent = failed(list) ? `读取不到模板：${list.error}` : '';
  if (failed(list)) return;
  state.templates = /** @type {import('../cli-types').Template[]} */ (list);
  $('route-template').replaceChildren(...state.templates.map((entry) => element('option', { value: entry.name, textContent: templateLabel(entry) })));
  $('route-template').value = chosenTemplate();
}

$('route-template').onchange = async () => {
  const result = await window.va.cliJson(['template', $('route-template').value, '--use']);
  if (result.error) alert(`没有换成：${result.error}`);
  await loadTemplates();
};

/** @returns {Promise<Partial<import('../cli-types').Template> & { error?: string }>} */
async function templateAction(name, flag) {
  const info = await window.va.cliJson(['template', name, flag]);
  if (info.error) alert(`没有成功：${info.error}`);
  await renderRules();
  return /** @type {any} */ (info);
}

export async function renderRules() {
  await loadTemplates();
  const button = (text, onclick, className = '') => element('button', { type: 'button', textContent: text, onclick, className });
  const status = (entry) =>
    (!entry.builtin ? '你自己的' : !entry.customized ? '自带' : entry.outdated ? '你改过；新版自带的这份有改动：打开对比，把要的改动合并进你的，再点「已合并」' : '你改过') +
    (entry.current ? ' · 正在用' : '');
  $('rules-list').replaceChildren(
    ...state.templates.map((entry) =>
      element('div', { className: 'rules-row' }, [
        element('strong', { textContent: entry.name }),
        element('span', { className: 'muted small-text', textContent: status(entry) }),
        button('编辑…', async () => {
          const info = await templateAction(entry.name, '--edit');
          if (info.path) window.va.open(info.path);
        }),
        ...(entry.outdated
          ? [
              button('打开新版对比', () => (entry.default && window.va.open(entry.default), window.va.open(entry.path))),
              button('已合并', () => templateAction(entry.name, '--accept')),
            ]
          : []),
        ...(entry.customized
          ? [button('恢复自带的', () => confirm(`删掉你改过的「${entry.name}」，回到自带的吗？`) && templateAction(entry.name, '--reset'), 'ghost')]
          : []),
        ...(!entry.builtin
          ? [button('删除', () => confirm(`删除模板「${entry.name}」吗？`) && templateAction(entry.name, '--reset'), 'ghost')]
          : []),
      ]),
    ),
  );
  const from = $('rules-new-from').value;
  $('rules-new-from').replaceChildren(...state.templates.map((entry) => element('option', { value: entry.name, textContent: entry.name })));
  $('rules-new-from').value = state.templates.some((entry) => entry.name === from) ? from : chosenTemplate();
}

$('rules-new').onclick = async () => {
  const name = $('rules-new-name').value.trim();
  if (!name) return $('rules-new-name').focus();
  const info = await window.va.cliJson(['template', $('rules-new-from').value, '--copy', name]);
  $('rules-status').textContent = failed(info) ? `没有新建：${info.error}` : `已新建「${name}」，在总结页上选它就按它写。`;
  if (failed(info)) return;
  $('rules-new-name').value = '';
  await renderRules();
  window.va.open(/** @type {import('../cli-types').Template} */ (info).path);
};
$('skill-view').onclick = async () => {
  $('skill-text').innerHTML = markdown(await window.va.readSkill());
  $('skill-dialog').showModal();
};
$('close-skill').onclick = () => $('skill-dialog').close();

// 关于: the version and licence, PRIVACY.md shown in a dialog, the licence and third-party notices opened as files.
export async function renderAbout() {
  const about = await window.va.about();
  $('about-text').textContent = `Video Agent ${about.version}。自由软件，以 GNU AGPL 3.0 或更高版本发布，不提供任何担保。`;
  $('about-privacy').onclick = () => {
    const text = about.privacy.replace(/^# .*\n+/, ''); // the dialog has the title
    $('privacy-text').innerHTML = markdown(text);
    $('privacy-dialog').showModal();
  };
  $('about-license').hidden = !about.license;
  $('about-license').onclick = () => about.license && window.va.open(about.license);
  $('about-notices').hidden = !about.notices;
  $('about-notices').onclick = () => about.notices && window.va.open(about.notices);
  $('about-source').onclick = () => window.va.external(SOURCE_PAGE);
}
$('close-privacy').onclick = () => $('privacy-dialog').close();

$('pick-workspace').onclick = async () => {
  const folder = await window.va.pickFolder('选择工作区');
  if (folder) $('set-workspace').value = folder;
};

$('set-provider').onchange = async () => {
  const config = await window.va.cliJson(['config', '--json', '--provider', $('set-provider').value]);
  if (!failed(config)) {
    $('set-model').value = config.model || '';
    $('set-base-url').value = config.base_url || '';
    $('api-info').textContent = `API key：${config.key || '还没有'}`;
  }
};

$('delete-key').onclick = async () => {
  const result = await window.va.cliText(['config', '--provider', $('set-provider').value, '--delete-key']);
  $('api-info').textContent = result.out.split('\n')[0] || result.err;
};

$('settings').addEventListener('close', async () => {
  if ($('settings').returnValue !== 'save') return;
  const workspaceChanged = $('set-workspace').value !== state.settings.workspace;
  state.settings = await window.va.saveSettings({
    workspace: $('set-workspace').value,
    cli: $('set-cli').value.trim(),
    // Left as they were shown, the agents stay as saved, so presets installed later still show while none were chosen.
    agents: JSON.stringify(agentRowsValue()) === agentRowsShown ? state.settings.agents : agentRowsValue(),
    closeToTray: $('set-close-to-tray').checked,
    compressDownloads: $('set-compress-downloads').checked,
    compressLocal: $('set-compress-local').checked,
    theme: $('set-theme').value,
    checkUpdates: $('set-check-updates').checked,
    // Kept only when it differs from the default, so a beta installed later still looks for betas.
    betaUpdates: $('set-beta-updates').checked === (state.appVersion || '').includes('-') ? undefined : $('set-beta-updates').checked,
    updateMirror: $('set-update-mirror').value.trim(),
    limits: Object.fromEntries(
      LIMITED.map((kind) => [kind, Math.min(8, Math.max(1, Number($(`set-limit-${kind}`).value) || 1))]),
    ),
  });
  const args = ['config', '--provider', $('set-provider').value];
  if ($('set-model').value.trim()) args.push('--model', $('set-model').value.trim());
  if ($('set-base-url').value.trim()) args.push('--base-url', $('set-base-url').value.trim());
  const key = $('set-key').value;
  if (key) args.push('--set-key');
  const result = await window.va.cliText(args, key ? key + '\n' : '');
  $('set-key').value = '';
  if (result.code !== 0) alert(`API 设置没有保存：${result.err || result.out}`);
  state.env = await window.va.env();
  renderVideo(); // the routes follow the agent chosen here
  if (workspaceChanged) await Promise.all(state.videos.map(refresh));
});
