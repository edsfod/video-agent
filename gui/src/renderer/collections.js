// Collections: the sidebar list and a collection's page (ARCHITECTURE.md, "Collections").

import { askSkip, renderSource } from './lists.js';
import { $, $$, baseName, CLI_JSON_VERSION, current, element, joinPath, markdown, state } from './state.js';
import { routeMissing } from './summary.js';
import { sameVideo, videoTask } from './task-panel.js';
import { addVideos, isVideo, renderList, select, showHome } from './video-list.js';
import { renderVideo } from './video-view.js';

// A collection is an ordered set of related videos with an overview and a study guide (ARCHITECTURE.md,
// "Collections"); everything goes through `video-agent collection`, `summarize --collection` and `pack --collection`.

/** @type {(...args: string[]) => ['collection', ...string[]]} */
const collectionArgs = (...args) => ['collection', ...args, '-o', state.settings.workspace];
export const currentCollection = () => state.collections.find((item) => item.name === state.collection) || null;
// The collection whose page is open, for the buttons on that page: they can be clicked only while it is shown.
export const pageCollection = () => /** @type {import('../cli-types').Collection} */ (currentCollection());

// A list that could not be read keeps the collections shown before (user report, 2026-10-29: one failed read while
// many tasks ended emptied 合集 and put every episode under 视频); it says so and is read again a little later.
// One read at a time: every video refreshed at start and every task that ends asks for one, and dozens running at once
// finished in any order, an older answer last. Asks that come while one runs share a single read after it.
let collectionRetry = null;
let collectionRead = null;
let collectionAgain = false;
export async function loadCollections() {
  if (collectionRead) {
    collectionAgain = true;
    return collectionRead;
  }
  collectionRead = readCollections();
  try {
    await collectionRead;
  } finally {
    collectionRead = null;
  }
  if (collectionAgain) {
    collectionAgain = false;
    await loadCollections();
  }
}

// A CLI set in the settings may be older or newer than this window, and print what it does not read.
export function cliMismatch(found) {
  if (found.error || found.json_version === CLI_JSON_VERSION) return null;
  const age = (found.json_version ?? 0) < CLI_JSON_VERSION ? '旧' : '新';
  return `用的 Video Agent 命令行比桌面程序${age}，两边的数据格式对不上，有些内容可能显示不出来或出错。在设置里清空「Video Agent 命令」，就会改用安装包自带的。`;
}

async function readCollections() {
  const result = await window.va.cliJson(collectionArgs('list'));
  clearTimeout(collectionRetry);
  if (Array.isArray(result)) {
    state.collections = result;
    state.collectionsError = null;
  } else {
    state.collectionsError = result?.error || '没有读到';
    collectionRetry = setTimeout(loadCollections, 5000);
  }
  renderList(); // also the collections
  if (state.view === 'collection') renderVideo();
}

// Each collection, and under it its videos when it is open: on its page, playing one of its videos, or opened with ▸.
// The sidebar lists collections only; their videos are opened from the collection's page, where there is room
// (user request, 2026-10-28). A collection holding the video shown is marked as well.
export function renderCollectionList() {
  const failed = state.collectionsError
    ? [element('p', { className: 'muted small-text collection-error', textContent: `合集列表这次没读到，几秒后再读：${(state.collectionsError.split('\n').pop() || '').slice(0, 160)}` })]
    : [];
  if (state.cliMismatch) failed.unshift(element('p', { className: 'muted small-text collection-error', textContent: state.cliMismatch }));
  $('collection-list').replaceChildren(
    ...failed,
    ...state.collections.map((item) => {
      const holdsCurrent = state.view === 'video' && item.videos.some((member) => isVideo(member.video, current()));
      const active = (state.view === 'collection' && item.name === state.collection) || holdsCurrent;
      const busy = item.videos.filter((member) => videoTask({ path: member.video })).length; // queued or running
      const row = element('div', { className: 'video-item collection-item' + (active ? ' active' : '') }, [
        element('span', { className: 'name', textContent: item.name, title: item.folder }),
        element('span', { className: 'badge', textContent: `${item.videos.length} 集` + (busy ? ` · ${busy} 个任务` : '') }),
      ]);
      // Its own page open: back to the start page; one of its videos open: to its page.
      row.onclick = () => (state.view === 'collection' && item.name === state.collection ? showHome() : openCollection(item.name));
      return row;
    }),
  );
}

// A collection's video opens on its own page; it is kept in the window's list of known videos, hidden from 视频.
function openMember(path) {
  const known = state.videos.find((video) => isVideo(path, video));
  return known ? select(known.path) : addVideos([path]);
}

export function openCollection(name) {
  state.view = 'collection';
  state.collection = name;
  renderList();
  renderCollectionList();
  renderVideo();
}

export async function collectionCommand(args, done = '') {
  const result = await window.va.cliJson(collectionArgs(...args));
  $('collection-state').textContent = result.error ? `没有成功：${result.error}` : done;
  await loadCollections();
  return !result.error;
}

// `compress --check` states that need no compressing: the button's text and its explanation.
export const COMPRESSION = {
  compressed: ['已压缩', '本程序已经压缩过这个视频'],
  efficient: ['不用压缩', '已经是 AV1、HEVC 或 VP9 编码，再压缩省不了多少'],
  'not-smaller': ['压缩过，没变小', '试过一次，压出来没有变小，原文件保留了'],
};

function memberBadges(member) {
  const badges = [];
  const add = (text, kind = '', title = '') => badges.push(element('span', { className: `badge ${kind}`, textContent: text, title }));
  if (member.skipped) add(`已跳过：${member.skipped}`);
  else if (member.summary) add('已总结', 'done');
  else add(member.processed ? '已处理' : '未处理');
  if (member.maybe_empty && !member.skipped) add('可能是空的', 'busy');
  if (COMPRESSION[member.compression]) add(...COMPRESSION[member.compression].slice(0, 1), 'muted', COMPRESSION[member.compression][1]);
  return badges;
}

export async function renderCollection() {
  const item = currentCollection();
  if (!item) {
    state.view = 'video';
    return renderVideo();
  }
  $('collection-name').textContent = item.name;
  $('collection-path').textContent = item.folder;
  renderSource(item);
  $('collection-members').replaceChildren(
    ...item.videos.map((member) => {
      const name = element('span', { className: 'name', textContent: member.name, title: member.video });
      name.onclick = () => openMember(member.video);
      const skip = element('button', { className: 'ghost small', textContent: member.skipped ? '不跳过' : '跳过' });
      skip.onclick = () => (member.skipped ? collectionCommand(['skip', item.name, member.video, '--reason', '']) : askSkip(member));
      const out = element('button', { className: 'ghost small', textContent: '移出', title: '只是移出合集，视频和它的总结都还在' });
      out.onclick = () => collectionCommand(['remove', item.name, member.video]);
      return element('div', { className: 'member' + (member.skipped ? ' skipped' : '') }, [
        element('span', { className: 'index', textContent: String(member.index) }),
        name,
        ...memberBadges(member),
        skip,
        out,
      ]);
    }),
  );
  if (!item.videos.length) {
    $('collection-members').replaceChildren(element('p', { className: 'muted', textContent: '还没有视频。在下面选一个加进来，或在视频页点「加入合集」。' }));
  }
  const others = state.videos.filter((video) => !item.videos.some((member) => isVideo(member.video, video)));
  $('collection-add-choice').replaceChildren(
    element('option', { value: '', textContent: others.length ? '从视频列表选一个…' : '视频列表里没有可加的视频' }),
    ...others.map((video) => element('option', { value: video.path, textContent: baseName(video.path) })),
  );
  $('collection-add-choice').disabled = !others.length;
  $('collection-add').disabled = true;
  const live = item.videos.filter((member) => !member.skipped);
  $('collection-process-all').disabled = !live.some((member) => !member.processed);
  $('collection-summarize-all').disabled = !live.some((member) => member.processed && !member.summary);
  const chosen = $('collection-route').value;
  for (const option of $('collection-route').querySelectorAll('.route-agent')) option.remove();
  $('collection-route').querySelector('option[value=api]').before(
    ...state.env.others.map(({ key, name }) => element('option', { className: 'route-agent', value: key, textContent: name })),
  );
  $('collection-route').value = chosen;
  if (!$('collection-route').value) $('collection-route').value = 'api';
  for (const option of $('collection-route').options) option.disabled = routeMissing(option.value);
  if ($('collection-route').selectedOptions[0]?.disabled) $('collection-route').value = 'api';
  const copying = $('collection-route').value === 'copy';
  $('collection-overview').textContent = copying ? '复制合集总结的材料' : item.overview ? '重新生成合集总结' : '生成合集总结';
  $('collection-guide').textContent = copying ? '复制学习提纲的材料' : item.guide ? '重新生成学习提纲' : '生成学习提纲';
  $('collection-import').hidden = !copying;
  $('collection-summarize-all').title = copying ? '复制材料这条路线不能批量总结；换一种总结方式' : '';
  $('collection-terms-count').textContent = item.terms.length ? `（${item.terms.length} 条）` : '';
  $('collection-terms').replaceChildren(
    ...item.terms.map(([wrong, right]) => {
      const undo = element('button', { className: 'ghost small', textContent: '撤销' });
      undo.onclick = () => collectionCommand(['terms', item.name, '--remove', wrong], `已撤销 ${wrong}`);
      return element('span', { className: 'correction' }, [element('span', { textContent: `${wrong} → ${right}` }), undo]);
    }),
  );
  for (const button of $$('.doc-tabs button')) button.classList.toggle('active', button.dataset.doc === state.doc);
  const file = state.doc === 'guide' ? item.guide : item.overview;
  // A summary changed after the overview or guide was written: say which, so it can be written again.
  const behind = (state.doc === 'guide' ? item.guide_behind : item.overview_behind) || [];
  $('collection-doc-behind').hidden = !file || !behind.length;
  $('collection-doc-behind').textContent =
    `第 ${behind.join('、')} 集的总结在这份${state.doc === 'guide' ? '学习提纲' : '合集总结'}写好之后改过，可以重新生成。`;
  const article = $('collection-doc');
  if (!file) {
    article.replaceChildren(element('p', { className: 'placeholder', textContent: state.doc === 'guide' ? '还没有学习提纲。' : '还没有合集总结。' }));
    return;
  }
  article.innerHTML = markdown((await window.va.read(file)) || '');
  for (const link of article.querySelectorAll('a[href]')) {
    const href = link.getAttribute('href');
    link.onclick = (event) => {
      event.preventDefault();
      if (/^https?:/.test(href)) return window.va.external(href);
      // Links to a video's summary open that video.
      const target = decodeURIComponent(href.replace(/^<|>$/g, '').replace(/#.*$/, ''));
      const member = item.videos.find((entry) => target.includes(baseName(entry.folder)));
      if (member && /总结\.md$/.test(target)) {
        const known = state.videos.find((video) => sameVideo(video.path, member.video));
        if (known) {
          state.tab = 'summary';
          return select(known.path);
        }
      }
      window.va.open(joinPath(item.folder, target));
    };
  }
}

for (const button of $$('.doc-tabs button')) {
  button.onclick = () => {
    state.doc = button.dataset.doc;
    renderCollection();
  };
}

$('collection-route').onchange = () => renderCollection();
$('collection-folder').onclick = () => window.va.open(pageCollection().folder);
$('collection-delete').onclick = async () => {
  const item = currentCollection();
  if (!item || !confirm(`删除合集「${item.name}」吗？各个视频和它们的总结都会保留，只删合集自己的文件（合集总结、学习提纲、共用术语）。`)) return;
  state.view = 'video';
  await collectionCommand(['delete', item.name]);
  renderVideo();
};
