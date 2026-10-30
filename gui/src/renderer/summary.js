// The 总结 tab: routes, models, versions, copying material and importing a text.

import { importCollection } from './lists.js';
import { $, $$, baseName, current, element, failed, joinPath, markdown, pageVideo, state } from './state.js';
import { ACTIVE, addTask, logAppend, sameVideo } from './task-panel.js';
import { chosenTemplate } from './templates.js';
import { when } from './updates.js';
import { refresh } from './video-list.js';
import { showImage } from './video-view.js';

const ROUTE_NOTES = {
  claude: '在后台运行 Claude Code，按 video-agent skill 写总结，会按需补截画面。使用你的 Claude 订阅。',
  codex: '在后台运行 Codex，按同一份 skill 写总结。使用你的 Codex 订阅。',
  api: '用设置里的模型 API 写总结（字幕和画面会发给该服务商）。支持工具调用的模型会按需补截画面。',
  deepseek: '在 DeepSeek 网页版里写总结：程序打开 DeepSeek 窗口（第一次要在里面登录），发去提示词和画面，开着深度思考和智能搜索，写完自动导入。之后每一轮请它对照字幕复查上一稿，补上漏掉的内容，并把程序查出的问题（缺的节、没写到的时间段）和它要补的画面一起发过去，直到复查不再补上或改正，最多 6 轮。每一轮都能在窗口里看到。',
  copy: '把规则、模板和字幕材料复制到剪贴板，贴进任何聊天 AI。要连画面一起给，用「导出 zip」；不收 zip、文件数有上限的（如 DeepSeek 网页版最多 50 个），用「导出文件夹」，屏幕页会拼成总图凑进上限。写好后用「导入总结」存回来，画面链接照样能点开。',
};

// Each other agent the settings show is a route of its own, keyed as in the settings (pi, hermes, dsh, custom).
const otherRoute = (route) => state.env.others.find((agent) => agent.key === route);
// The route's name in task titles; another agent goes by the name the settings give it.
export const routeName = (route) =>
  ({ api: '模型 API', claude: 'Claude Code', codex: 'Codex', deepseek: 'DeepSeek 网页' })[route] || otherRoute(route)?.name;
export const routeMissing = (route) =>
  (route === 'claude' && !state.env.claude) || (route === 'codex' && !state.env.codex) || otherRoute(route)?.found === false;
const routeNote = (route) =>
  (!route && '选一种总结方式。') ||
  ROUTE_NOTES[route] ||
  (otherRoute(route)
    ? `在后台运行 ${otherRoute(route)?.name}，按同一份 skill 写总结。它以你的身份运行命令，不限于工作区。`
    : '还没有其他 Agent：在「设置」→「其他 Agent」里勾上 pi、Hermes Agent、DeepSeek Harness，或填你自己的命令。');

// With no other agent, a 其他 Agent route still shows, so it can be found, and says where to add one.
function otherRouteLabels() {
  const others = state.env.others.length ? state.env.others : [{ key: 'other', name: '其他 Agent' }];
  return others.map(({ key, name }) =>
    element('label', { className: 'route-agent' }, [element('input', { type: 'radio', name: 'route', value: key }), ` ${name}`]),
  );
}

// The model and thinking level each route runs with, chosen on the summary page and kept per route (user requests,
// 2026-10-29: not only the configured default, for agents too, from a full list read without spending tokens, and
// the thinking level). Empty means the route's own default. The lists come from models.js through the main process,
// read once per route while the window is open; a model not in the list is typed in under 自定义….
const CUSTOM_MODEL = '\u0000custom';
export const modelFor = (route) => (state.settings.routeModels || {})[route] || '';
export const effortFor = (route) => (state.settings.routeEfforts || {})[route] || '';
export const modelTakes = (route) => ['api', 'claude', 'codex'].includes(route) || !!otherRoute(route)?.model;
const modelLists = {};

async function saveRouteChoice(changes) {
  state.settings = await window.va.saveSettings(changes);
}

async function renderModel() {
  const route = state.route;
  $('route-model-label').hidden = !route || !modelTakes(route);
  if (!route || !modelTakes(route)) return;
  const select = $('route-model');
  const fill = (list, note) => {
    if (route !== state.route) return; // another route was chosen meanwhile
    const saved = modelFor(route);
    const known = list.models.some((model) => model.value === saved);
    select.replaceChildren(
      element('option', { value: '', textContent: route === 'api' ? '默认（设置里的模型）' : `默认（${routeName(route)} 自己的设置）` }),
      ...list.models.map((model) => element('option', { value: model.value, textContent: model.label })),
      element('option', { value: CUSTOM_MODEL, textContent: '自定义…' }),
    );
    select.value = !saved ? '' : known ? saved : CUSTOM_MODEL;
    $('route-model-custom').hidden = select.value !== CUSTOM_MODEL;
    if (select.value === CUSTOM_MODEL) $('route-model-custom').value = saved;
    // Codex lists the levels each model takes; the others one list for all.
    const levels = list.models.find((model) => model.value === saved)?.efforts || list.efforts;
    $('route-effort-label').hidden = !levels.length;
    $('route-effort').replaceChildren(
      element('option', { value: '', textContent: '默认' }),
      ...levels.map((level) => element('option', { value: level, textContent: level })),
    );
    $('route-effort').value = levels.includes(effortFor(route)) ? effortFor(route) : '';
    $('route-model-note').textContent = note || '';
  };
  if (!modelLists[route]) {
    fill({ models: [], efforts: [] }, '正在读取模型列表…');
    modelLists[route] = window.va.models(route).catch((error) => ({ models: [], efforts: [], error: error.message }));
  }
  const list = await modelLists[route];
  if (list.error) delete modelLists[route]; // asked again next time
  fill(list, list.error ? `读不到模型列表：${list.error}。可以选「自定义…」自己填。` : list.models.length ? '' : '没有读到模型列表，可以选「自定义…」自己填。');
}

$('route-model').onchange = async () => {
  const custom = $('route-model').value === CUSTOM_MODEL;
  $('route-model-custom').hidden = !custom;
  if (custom) return $('route-model-custom').focus();
  await saveRouteChoice({ routeModels: { ...(state.settings.routeModels || {}), [String(state.route)]: $('route-model').value } });
  renderModel(); // the thinking levels may follow the model
};
$('route-model-custom').onchange = () =>
  saveRouteChoice({ routeModels: { ...(state.settings.routeModels || {}), [String(state.route)]: $('route-model-custom').value.trim() } });
$('route-effort').onchange = () =>
  saveRouteChoice({ routeEfforts: { ...(state.settings.routeEfforts || {}), [String(state.route)]: $('route-effort').value } });

function renderRoutes() {
  for (const label of $$('#routes .route-agent')) label.remove();
  $('routes').querySelector('input[value=api]').parentElement.before(...otherRouteLabels());
  if (state.route && !document.querySelector(`input[name=route][value="${state.route}"]`)) state.route = null;
  for (const input of $$('input[name=route]')) {
    const missing = routeMissing(input.value);
    input.disabled = missing;
    input.parentElement.classList.toggle('unavailable', missing);
    input.parentElement.title = missing ? `没有找到 ${otherRoute(input.value)?.file || input.value} 命令` : '';
    input.checked = input.value === state.route;
    input.onchange = () => {
      state.route = input.value;
      renderSummary(current());
    };
  }
  $('route-note').textContent = routeNote(state.route);
  renderModel();
}

export async function renderSummary(video) {
  renderRoutes();
  const article = $('summary');
  const info = video.info;
  $('run-summary').disabled = !info?.processed || !state.route || state.route === 'other';
  $('run-summary').textContent = state.route === 'copy' ? '复制材料' : info?.summary ? '重新生成总结' : '生成总结';
  $('open-summary').hidden = !info?.summary;
  const copying = state.route === 'copy' && !!info?.processed;
  for (const id of ['export-zip', 'export-folder', 'export-limit-label', 'import-summary']) $(id).hidden = !copying;
  $('export-limit').value = state.settings.webFiles || 50;
  if (!info?.processed) {
    $('summary-versions').hidden = true;
    article.replaceChildren(element('p', { className: 'placeholder', textContent: '先在「处理」里处理这个视频，再生成总结。' }));
    return;
  }
  if (!info.summary) {
    $('summary-versions').hidden = true;
    article.replaceChildren(element('p', { className: 'placeholder', textContent: '还没有总结。' }));
    return;
  }
  // Versions live beside 总结.md (versions.py), so the links in any of them resolve from the same folder.
  const found = await window.va.cliJson(['versions', video.path, '-o', state.settings.workspace, '--json']);
  const list = failed(found) ? { current: null, versions: [] } : found;
  const chosen = state.version;
  if (!chosen || chosen.video !== video.path || !list.versions.some((entry) => entry.file === chosen.file)) {
    state.version = null;
  }
  renderVersions(list);
  const version = state.version;
  const shown = (version && list.versions.find((entry) => entry.file === version.file)?.path) || info.summary;
  const text = await window.va.read(shown);
  article.innerHTML = markdown(text || '');
  if (state.version) {
    article.prepend(element('p', { className: 'version-banner', textContent: '正在看另一个版本；点「设为当前」才会换掉现在的总结。' }));
  }
  for (const link of article.querySelectorAll('a[href]')) {
    const href = link.getAttribute('href');
    link.onclick = (event) => {
      event.preventDefault();
      if (/^https?:/.test(href)) return window.va.external(href);
      const target = decodeURIComponent(href.replace(/^<|>$/g, ''));
      const file = /^[a-z]:/i.test(target) ? target.replace(/\//g, '\\') : joinPath(info.folder, target);
      if (/\.(jpe?g|png)$/i.test(file)) showImage(file, target);
      else window.va.open(file);
    };
  }
}

const versionLabel = (entry) => [when(entry.created), entry.source, entry.note].filter(Boolean).join(' · ');

function renderVersions(list) {
  state.versionList = list;
  const others = list.versions;
  $('summary-versions').hidden = !others.length && !list.current?.note;
  $('summary-version-pick').replaceChildren(
    element('option', { value: '', textContent: `当前：${list.current ? versionLabel(list.current) : ''}` }),
    ...others.map((entry) => element('option', { value: entry.file, textContent: versionLabel(entry) })),
  );
  $('summary-version-pick').value = state.version?.file || '';
  $('summary-version-use').disabled = $('summary-version-delete').disabled = !state.version;
}

const versionArgs = (...args) => ['versions', pageVideo().path, '-o', state.settings.workspace, ...args];
$('summary-version-pick').onchange = () => {
  const file = $('summary-version-pick').value;
  state.version = file ? { video: pageVideo().path, file } : null;
  renderSummary(current());
};
// The version shown, for its buttons, which show only with one.
const chosenVersion = () => /** @type {{ video: string, file: string }} */ (state.version).file;
$('summary-version-use').onclick = async () => {
  const result = await window.va.cliText(versionArgs('--use', chosenVersion()));
  if (result.code !== 0) return alert(`没有换成：${(result.err || result.out).trim()}`);
  state.version = null;
  summaryState('已换成这个版本；原来的总结留作一个版本。');
  await refresh(current());
};
$('summary-version-delete').onclick = async () => {
  if (!confirm('删除这个版本？删除后找不回来。')) return;
  const result = await window.va.cliText(versionArgs('--delete', chosenVersion()));
  if (result.code !== 0) return alert(`没有删除：${(result.err || result.out).trim()}`);
  state.version = null;
  await refresh(current());
};
// Electron has no window.prompt(), so the note is edited in a dialog of its own, starting from the note it has.
$('summary-version-note').onclick = () => {
  const list = state.versionList;
  const version = state.version;
  const shown = version ? list?.versions.find((entry) => entry.file === version.file) : list?.current;
  $('note-text').value = shown?.note || '';
  $('note-dialog').showModal();
  $('note-text').select();
};
$('note-text').onkeydown = (event) => {
  if (event.key !== 'Enter' || event.isComposing) return;
  event.preventDefault();
  $('note-dialog').close('save');
};
$('note-dialog').addEventListener('close', async () => {
  if ($('note-dialog').returnValue !== 'save') return;
  const file = state.version?.file || '总结.md';
  const result = await window.va.cliText(versionArgs('--note', file, $('note-text').value.trim()));
  if (result.code !== 0) return alert(`没有保存备注：${(result.err || result.out).trim()}`);
  renderSummary(current());
});

$('open-summary').onclick = () => {
  const summary = pageVideo().info?.summary;
  if (summary) window.va.open(summary);
};

$('run-summary').onclick = async () => {
  const video = pageVideo();
  const info = video.info;
  const route = state.route;
  if (!info || !route) return; // not read yet, or no route chosen
  const request = $('summary-request').value.trim();
  if (route === 'copy') return copyMaterial();
  const name = routeName(route);
  // A summary there already stays current; the new one is kept as a version to compare and choose.
  if (info.summary) summaryState('已经有总结：新写的会另存为一个版本，原来的不动。');
  addTask({
    kind: 'summary',
    title: `总结（${name}）：${baseName(video.path)}`,
    route,
    agent: ['api', 'deepseek'].includes(route) ? undefined : route,
    maxFiles: route === 'deepseek' ? state.settings.webFiles || 50 : undefined,
    video: video.path,
    folder: info.folder,
    request,
    overwrite: false,
  });
};

// Claude Code stream-json: show text and tool calls; skip the rest.
export function claudeLine(line) {
  let event;
  try {
    event = JSON.parse(line);
  } catch {
    return logAppend(line + '\n');
  }
  if (event.type === 'assistant') {
    for (const block of event.message?.content || []) {
      if (block.type === 'text' && block.text.trim()) logAppend(block.text.trim() + '\n');
      if (block.type === 'tool_use') {
        const input = block.input || {};
        logAppend(`▸ ${block.name}: ${input.command || input.file_path || input.skill || ''}\n`);
      }
    }
  } else if (event.type === 'result') {
    if (event.is_error) logAppend(`出错：${event.result || event.subtype}\n`);
    const cost = event.total_cost_usd ? `，约 ${event.total_cost_usd.toFixed(2)} 美元` : '';
    logAppend(`\n用时 ${Math.round((event.duration_ms || 0) / 1000)} 秒，${event.num_turns} 轮${cost}\n`);
  }
}

// Codex exec --json: show commands and messages.
export function codexLine(line) {
  let event;
  try {
    event = JSON.parse(line);
  } catch {
    return logAppend(line + '\n');
  }
  if (event.type === 'error' || event.type === 'turn.failed') {
    return logAppend(`出错：${event.message || event.error?.message}\n`);
  }
  const item = event.item;
  if (event.type !== 'item.completed' || !item) return;
  if (item.type === 'error') return logAppend(`提示：${item.message}\n`);
  if (item.type === 'command_execution') logAppend(`▸ ${item.command}\n`);
  else if (item.type === 'agent_message' && item.text) logAppend(item.text.trim() + '\n');
}

// The prompt comes from the CLI (`pack`), the same text the zip holds.
const packArgs = (video) => [
  'pack', video.path, '-o', state.settings.workspace, '--request', $('summary-request').value.trim(), '--template', chosenTemplate(),
];

let summaryTimer;
function summaryState(text) {
  $('summary-state').textContent = text;
  clearTimeout(summaryTimer);
  summaryTimer = setTimeout(() => ($('summary-state').textContent = ''), 10000);
}

async function copyMaterial() {
  const result = await window.va.cliText(packArgs(current()));
  if (result.code !== 0) return alert(`没有复制：${result.err || result.out}`);
  await window.va.copy(result.out);
  summaryState(`已复制 ${result.out.length} 个字符。画面没有一起复制；要连画面一起给，用「导出 zip」。`);
}

$('export-zip').onclick = async () => {
  const video = pageVideo();
  const file = await window.va.pickSave('导出给网页 AI 的材料', `${baseName(video.path).replace(/\.[^.]+$/, '')}-材料.zip`);
  if (!file) return;
  summaryState('正在打包…');
  const result = await window.va.cliText([...packArgs(video), '--zip', file]);
  if (result.code !== 0) return summaryState(`没有导出：${(result.err || result.out).trim()}`);
  summaryState(`已导出：${result.out.trim()}。把 提示词.md 和图片交给网页 AI；不收 zip 的，就解压后上传。`);
  window.va.reveal(file);
};

// For chat AIs that take files one by one up to a limit (user request, 2026-10-28): the prompt and numbered pictures.
$('export-folder').onclick = async () => {
  const video = pageVideo();
  const limit = Math.max(2, Number($('export-limit').value) || 50);
  if (limit !== state.settings.webFiles) state.settings = await window.va.saveSettings({ webFiles: limit });
  const parent = await window.va.pickFolder('导出到哪个文件夹（会在里面新建一个文件夹）');
  if (!parent) return;
  summaryState('正在导出…');
  const result = await window.va.cliText([...packArgs(video), '--folder', parent, '--max-files', String(limit)]);
  if (result.code !== 0) return summaryState(`没有导出：${(result.err || result.out).trim()}`);
  const folder = result.out.trim().replace(/ \(\d+ pictures\)$/, '');
  summaryState(`已导出到 ${baseName(folder)}：把里面的文件全部交给网页 AI，提示词.md 也是其中一个。`);
  window.va.reveal(folder);
};

// A video with a running or queued processing or summary task would be written twice.
function busyWriting(video) {
  return state.tasks.some((task) => ACTIVE.has(task.status) && ['process', 'summary'].includes(task.kind) && sameVideo(task.video, video.path));
}

/** @type {string | null} a file chosen to import instead of the pasted text */
export let importFile = null;
/** @type {{ collection: string, guide: boolean } | null} null for the current video */
export let importTarget = null;

$('import-summary').onclick = () => {
  if (busyWriting(current())) return alert('这个视频正在处理或总结，等任务结束再导入。');
  openImport();
};

/** @param {{ collection: string, guide: boolean } | null} [target] null for the current video */
export function openImport(target = null) {
  importTarget = target;
  importFile = null;
  $('import-text').value = '';
  $('import-file-name').textContent = '';
  $('import-note').value = '';
  $('import-current').checked = false;
  // Choosing only matters with something there already; the first text becomes current anyway.
  const item = target && state.collections.find((entry) => entry.name === target.collection);
  const exists = target ? (target.guide ? item?.guide : item?.overview) : current()?.info?.summary;
  $('import-current-label').hidden = !exists;
  $('import-dialog').showModal();
}

$('import-file').onclick = async () => {
  importFile = await window.va.pickFile('选择总结文件', [{ name: 'Markdown', extensions: ['md', 'markdown', 'txt'] }]);
  $('import-file-name').textContent = importFile ? `将导入 ${baseName(importFile)}（文本框里的内容不用）` : '';
};

$('import-dialog').addEventListener('close', async () => {
  if ($('import-dialog').returnValue !== 'save') return;
  const text = $('import-text').value;
  if (!importFile && !text.trim()) return;
  if (importTarget) return importCollection(text);
  const video = pageVideo();
  const args = ['summarize', video.path, '-o', state.settings.workspace, '--import', importFile || '-', '--source', '网页 AI'];
  const note = $('import-note').value.trim();
  if (note) args.push('--note', note);
  const asCurrent = !video.info?.summary || $('import-current').checked;
  if (asCurrent) args.push('--make-current');
  const result = await window.va.cliText(args, importFile ? '' : text);
  if (result.code !== 0) return alert(`没有导入：${(result.err || result.out).trim()}`);
  const fixed = /applied (\d+) transcript corrections/.exec(result.err)?.[1];
  summaryState(
    (asCurrent ? '已导入，设为当前总结。' : '已导入，另存为一个版本；在上面的「版本」里查看或设为当前。') +
      (fixed ? `按总结里的「字幕改正」改了 ${fixed} 处错字，原字幕保留。` : ''),
  );
  await refresh(video);
});
