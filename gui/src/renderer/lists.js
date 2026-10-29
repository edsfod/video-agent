// Adding to collections and downloading lists: the collection dialogs, a list found at a link, following it.

import { collectionCommand, COMPRESSION, currentCollection, loadCollections, openCollection, pageCollection } from './collections.js';
import { $, baseName, current, element, pageVideo, state } from './state.js';
import { importFile, importTarget, openImport, routeName } from './summary.js';
import { ACTIVE, addTask, sameVideo } from './task-panel.js';
import { chosenTemplate } from './templates.js';
import { addLocalVideos, addVideos, refresh } from './video-list.js';
import { downloaded, renderVideo } from './video-view.js';

const CHECK_EVERY_MS = 6 * 3600 * 1000;

export function renderSource(item) {
  const source = item.source;
  $('collection-following').hidden = !source;
  $('collection-follow-form').hidden = Boolean(source);
  if (!source) return;
  const when = source.checked ? new Date(source.checked).toLocaleString('zh-CN') : '还没检查过';
  const found = source.checked ? `，上次新增 ${source.new} 个` : '';
  const running = state.tasks.some((task) => ACTIVE.has(task.status) && task.update === item.name);
  $('collection-source-info').textContent = `${source.url} · 新视频存到 ${source.folder} · 上次检查：${when}${found}`;
  $('collection-check').disabled = running;
  $('collection-check').textContent = running ? '正在检查…' : '检查新视频';
  $('collection-auto').checked = Boolean(source.auto);
}

function checkSource(item) {
  return addTask({
    kind: 'download',
    title: `检查新视频：${item.name}`,
    url: item.source.url, // for the site's cookies and so the same list is not checked twice at once
    update: item.name,
    then: state.settings.processAfterDownload !== false ? 'process' : undefined,
  });
}

$('collection-check').onclick = () => checkSource(currentCollection()).then(() => renderVideo());
$('collection-auto').onchange = () =>
  collectionCommand(['follow', pageCollection().name, $('collection-auto').checked ? '--auto' : '--no-auto']);
$('collection-unfollow').onclick = () => collectionCommand(['unfollow', pageCollection().name], '不再跟踪这个列表');
$('collection-follow-form').onsubmit = async (event) => {
  event.preventDefault();
  const url = $('collection-follow-url').value.trim();
  if (!url) return;
  if (await collectionCommand(['follow', pageCollection().name, url], '已跟踪；点「检查新视频」下载还没有的')) {
    $('collection-follow-url').value = '';
  }
};

// Lists set to check on their own: a while after start, then every six hours, while the app runs (also in the tray).
function checkFollowed() {
  for (const item of state.collections.filter((entry) => entry.source?.auto)) checkSource(item);
}
setTimeout(checkFollowed, 60 * 1000);
setInterval(checkFollowed, CHECK_EVERY_MS);

$('collection-add-choice').onchange = () => ($('collection-add').disabled = !$('collection-add-choice').value);
$('collection-add').onclick = () => {
  const path = $('collection-add-choice').value;
  if (path) collectionCommand(['add', pageCollection().name, path]);
};
// Local files go into the video list too, so they can be processed from there.
$('collection-add-files').onclick = async () => {
  const paths = await window.va.pickVideos();
  if (!paths?.length) return;
  await addLocalVideos(paths);
  await collectionCommand(['add', pageCollection().name, ...paths]);
};
// Every video of the collection; compress itself skips those compressed before or already efficient. Videos that are
// not this program's downloads are the user's own files: replaced only with the setting on, or after asking here.
$('collection-compress-all').onclick = async () => {
  // Checked first (user request, 2026-10-29): those compressed already, or not worth it, are not queued at all.
  const candidates = pageCollection().videos.filter((entry) => !entry.skipped);
  $('collection-state').textContent = '正在检查哪些已经压缩过…';
  const checked = candidates.length ? await window.va.cliText(['compress', '--check', '--json', ...candidates.map((member) => member.video)]) : { out: '' };
  const states = new Map(
    checked.out.split('\n').filter((line) => line.trim().startsWith('{')).map((line) => JSON.parse(line)).map((entry) => [entry.video.toLowerCase(), entry]),
  );
  const members = candidates.filter((member) => {
    const entry = states.get(member.video.toLowerCase());
    return entry && !entry.error && !COMPRESSION[entry.state];
  });
  const done = candidates.length - members.length;
  loadCollections(); // the badges follow what was found
  const own = members.filter((member) => !downloaded({ path: member.video }));
  if (own.length && !state.settings.compressLocal) {
    const asked = `其中 ${own.length} 集不是本程序下载的，是你电脑上的文件。压缩会用压缩后的文件替换它们，原文件不保留。也压缩这几集吗？\n\n选「取消」只压缩本程序下载的 ${members.length - own.length} 集。`;
    if (!confirm(asked)) members.splice(0, members.length, ...members.filter((member) => !own.includes(member)));
  }
  for (const member of members) {
    if (!state.videos.some((video) => sameVideo(video.path, member.video))) await addVideos([member.video], { show: false });
    await addTask({ kind: 'compress', title: `压缩：${baseName(member.video)}`, video: member.video });
  }
  const skipped = done ? `${done} 集已经压缩过、不用压缩或找不到文件，没有排进去。` : '';
  $('collection-state').textContent = members.length ? `已把 ${members.length} 集排进压缩。${skipped}` : `没有要压缩的。${skipped}`;
};

$('collection-process-all').onclick = async () => {
  for (const member of pageCollection().videos.filter((entry) => !entry.skipped && !entry.processed)) {
    if (!state.videos.some((video) => sameVideo(video.path, member.video))) await addVideos([member.video]);
    await addTask({
      kind: 'process',
      title: `处理：${baseName(member.video)}`,
      video: member.video,
      interval: state.settings.frameInterval,
      maxFrames: state.settings.maxFrames || null,
    });
  }
};
$('collection-summarize-all').onclick = async () => {
  const route = $('collection-route').value;
  if (route === 'copy') return alert('复制材料这条路线要一集一集地在网页 AI 里写，不能批量。换成 Claude Code、Codex 或模型 API。');
  const name = routeName(route);
  for (const member of pageCollection().videos.filter((entry) => !entry.skipped && entry.processed && !entry.summary)) {
    await addTask({
      kind: 'summary',
      title: `总结（${name}）：${baseName(member.video)}`,
      route,
      agent: route === 'api' ? undefined : route,
      video: member.video,
      folder: member.folder,
      request: '',
      overwrite: false,
    });
  }
};

async function writeCollectionFile(guide) {
  const item = pageCollection();
  const route = $('collection-route').value;
  const request = $('collection-request').value.trim();
  const file = guide ? '学习提纲' : '合集总结';
  if (route === 'copy') {
    const args = ['pack', '--collection', item.name, '-o', state.settings.workspace, '--request', request, '--template', chosenTemplate()];
    if (guide) args.push('--guide');
    const result = await window.va.cliText(args);
    if (result.code !== 0) return ($('collection-state').textContent = `没有复制：${(result.err || result.out).trim()}`);
    await window.va.copy(result.out);
    $('collection-state').textContent = `已复制${file}的材料（${result.out.length} 个字符）。在网页 AI 里写好后点「导入…」存回来。`;
    return;
  }
  const exists = guide ? item.guide : item.overview;
  if (exists) $('collection-state').textContent = `已经有${file}：新写的会另存为一个版本，原来的不动。`;
  const missing = item.videos.filter((member) => !member.skipped && !member.summary);
  if (route === 'api' && missing.length) {
    return alert(`还有 ${missing.length} 集没有总结：${missing.map((member) => member.name).join('、')}。先点「总结没总结的」，或把没内容的跳过。`);
  }
  const name = routeName(route);
  await addTask({
    kind: 'collection',
    title: `${file}（${name}）：${item.name}`,
    collection: item.name,
    video: `合集:${item.name}`,
    folder: item.folder,
    guide,
    route,
    agent: route === 'api' ? undefined : route,
    request,
    overwrite: false,
  });
}
$('collection-overview').onclick = () => writeCollectionFile(false);
$('collection-guide').onclick = () => writeCollectionFile(true);
$('collection-import').onclick = () => {
  openImport({ collection: pageCollection().name, guide: state.doc === 'guide' });
};

export async function importCollection(text) {
  const { collection, guide } = /** @type {{ collection: string, guide: boolean }} */ (importTarget); // set for a collection
  const item = state.collections.find((entry) => entry.name === collection);
  const exists = guide ? item?.guide : item?.overview;
  const args = ['summarize', '--collection', collection, '-o', state.settings.workspace, '--import', importFile || '-', '--source', '网页 AI'];
  if (guide) args.push('--guide');
  const note = $('import-note').value.trim();
  if (note) args.push('--note', note);
  if (!exists || $('import-current').checked) args.push('--make-current');
  const result = await window.va.cliText(args, importFile ? '' : text);
  if (result.code !== 0) return alert(`没有导入：${(result.err || result.out).trim()}`);
  $('collection-state').textContent = `已导入${guide ? '学习提纲' : '合集总结'}。`;
  await loadCollections();
}

$('collection-terms-form').onsubmit = async (event) => {
  event.preventDefault();
  const wrong = $('collection-term-wrong').value.trim();
  const right = $('collection-term-right').value.trim();
  if (!wrong || !right || wrong === right) return;
  if (await collectionCommand(['terms', pageCollection().name, '--replace', wrong, right], `已改正 ${wrong} → ${right}，各集的整理版字幕已更新`)) {
    $('collection-term-wrong').value = '';
    $('collection-term-right').value = '';
    await Promise.all(state.videos.map(refresh));
  }
};

// One dialog to make a collection (from the sidebar) or to put the current video into one (from the video view).
let joining = null; // the video to add, or null when only making a collection

function openCollectionDialog(video) {
  joining = video;
  $('collection-dialog-title').textContent = video ? `把「${baseName(video)}」加入合集` : '新建合集';
  $('collection-dialog-pick').hidden = !video || !state.collections.length;
  $('collection-dialog-choice').replaceChildren(
    element('option', { value: '', textContent: '（新建）' }),
    ...state.collections.map((item) => element('option', { value: item.name, textContent: item.name })),
  );
  $('collection-dialog-new').textContent = video ? '或者新建一个合集，名字' : '合集的名字';
  $('collection-dialog-name').value = '';
  $('collection-dialog').showModal();
}

$('new-collection').onclick = () => openCollectionDialog(null);
$('join-collection').onclick = () => openCollectionDialog(pageVideo().path);
$('collection-dialog').addEventListener('close', async () => {
  if ($('collection-dialog').returnValue !== 'save') return;
  const existing = joining ? $('collection-dialog-choice').value : '';
  const name = existing || $('collection-dialog-name').value.trim();
  if (!name) return;
  const videos = joining ? [joining] : [];
  const ok = existing
    ? await collectionCommand(['add', name, ...videos])
    : await collectionCommand(['create', name, ...videos]);
  if (ok) openCollection(name);
  else alert($('collection-state').textContent);
});

let skipping = null;
export function askSkip(member) {
  skipping = member;
  $('skip-dialog-video').textContent = member.name;
  $('skip-dialog-reason').value = member.maybe_empty ? '几乎没有内容' : '';
  $('skip-dialog').showModal();
}
$('skip-dialog').addEventListener('close', () => {
  if ($('skip-dialog').returnValue !== 'save' || !skipping) return;
  const reason = $('skip-dialog-reason').value.trim() || '跳过';
  collectionCommand(['skip', pageCollection().name, skipping.video, '--reason', reason]);
});
