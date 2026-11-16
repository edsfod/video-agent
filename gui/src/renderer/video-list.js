// The 视频 list in the sidebar: adding videos, reading each one's state, choosing one.

import { loadCollections, renderCollectionList } from './collections.js';
import { $, baseName, element, failed, state } from './state.js';
import { addTask, sameVideo, videoTask } from './task-panel.js';
import { renderVideo } from './video-view.js';

// `show: false` adds them without opening the last one, for downloads that fill a collection in the background.
export async function addVideos(paths, { show = true } = {}) {
  for (const path of paths) {
    if (!state.videos.some((video) => video.path.toLowerCase() === path.toLowerCase())) {
      state.videos.push({ path, info: null });
    }
  }
  await persistList();
  renderList();
  if (paths.length && show) await select(paths[paths.length - 1]);
  await Promise.all(state.videos.filter((video) => !video.info).map(refresh));
}

// Videos the user adds from disk are processed at once when 下载或添加后自动处理 is on, so a subtitle file beside one
// (same name) is read in without a click (user request, 2026-10-28). A local video's audio is not uploaded by default:
// for those without subtitles the window asks first (BCut, the pictures only, or later).
export async function addLocalVideos(paths) {
  if (!paths?.length) return;
  await addVideos(paths);
  if (state.settings.processAfterDownload === false) return;
  const fresh = state.videos.filter(
    (entry) => paths.some((path) => sameVideo(entry.path, path)) && entry.info && !entry.info.processed,
  );
  // With 也压缩本地添加的视频 on (the user agreed to have the files replaced), a video is compressed first.
  const process = (video, bcut) => {
    const compress = state.settings.compressLocal === true;
    return addTask({
      kind: compress ? 'compress' : 'process',
      title: `${compress ? '压缩' : '处理'}：${baseName(video.path)}`,
      video: video.path,
      then: compress ? 'process' : undefined,
      interval: state.settings.frameInterval,
      maxFrames: state.settings.maxFrames,
      bcut,
    });
  };
  for (const video of fresh.filter((entry) => entry.info?.subtitles)) await process(video, false);
  const bare = fresh.filter((entry) => !entry.info?.subtitles);
  if (!bare.length) return;
  $('nosubs-list').replaceChildren(...bare.map((video) => element('li', { textContent: baseName(video.path) })));
  $('nosubs-dialog').returnValue = '';
  $('nosubs-dialog').showModal();
  await new Promise((resolve) => $('nosubs-dialog').addEventListener('close', resolve, { once: true }));
  const choice = $('nosubs-dialog').returnValue;
  if (choice === 'bcut' || choice === 'pictures') for (const video of bare) await process(video, choice === 'bcut');
}

export async function persistList() {
  state.settings = await window.va.saveSettings({ videos: state.videos.map((video) => video.path) });
}

function badge(video) {
  const task = videoTask(video);
  if (task) {
    const doing = task.status === 'queued' ? '排队中' : { process: '处理中', summary: '总结中', frame: '补截中', compress: '压缩中' }[task.kind];
    return element('span', { className: 'badge busy', textContent: doing });
  }
  if (video.error) return element('span', { className: 'badge error', textContent: '无法读取' });
  if (!video.info) return element('span', { className: 'badge', textContent: '…' });
  if (video.info.summary) return element('span', { className: 'badge done', textContent: '已总结' });
  if (video.info.processed) return element('span', { className: 'badge', textContent: '已处理' });
  return element('span', { className: 'badge', textContent: '未处理' });
}

// The window keeps a path as it was added; the CLI, and so a collection, holds it resolved (a short 8.3 name such as
// RUNNER~1 in %TEMP% comes back long). A video matches a path by either.
export const isVideo = (path, video) => [video?.path, video?.info?.video].some((own) => sameVideo(own, path));
// A video in a collection is listed under the collection in the sidebar, not here (user decision, 2026-10-28).
export const inCollection = (video) => state.collections.some((item) => item.videos.some((member) => isVideo(member.video, video)));

export function renderList() {
  const list = $('video-list');
  const shown = state.videos.filter((video) => !inCollection(video));
  const chosen = state.chosen;
  list.replaceChildren(
    ...shown.map((video) => {
      const active = state.view === 'video' && video.path === state.current;
      const text = [element('span', { className: 'name', textContent: baseName(video.path), title: video.path }), badge(video)];
      if (chosen) {
        const ticked = chosen.has(video.path);
        const box = element('input', { type: 'checkbox', checked: ticked, tabIndex: -1 });
        const item = element('div', { className: 'video-item choosing' + (ticked ? ' chosen' : '') }, [
          box,
          element('span', { className: 'text' }, text),
        ]);
        item.onclick = () => {
          if (ticked) chosen.delete(video.path);
          else chosen.add(video.path);
          renderList();
        };
        return item;
      }
      const item = element('div', { className: 'video-item' + (active ? ' active' : '') }, text);
      item.onclick = () => (active ? showHome() : select(video.path));
      return item;
    }),
  );
  $('choose-videos').textContent = chosen ? '完成' : '选择';
  $('choose-videos').hidden = !shown.length && !chosen;
  $('delete-chosen').hidden = !chosen;
  $('delete-chosen').disabled = !chosen?.size;
  $('delete-chosen').textContent = chosen?.size ? `删除 ${chosen.size} 个` : '删除';
  if (!shown.length && state.videos.length) {
    list.append(element('p', { className: 'muted small-text list-note', textContent: '视频都在上面的合集里。' }));
  }
  renderCollectionList();
}

export async function refresh(video) {
  const info = await window.va.cliJson(['show', video.path, '-o', state.settings.workspace]);
  if (info.error) {
    video.error = info.error;
    video.info = null;
  } else {
    video.error = null;
    video.info = info;
  }
  renderList();
  if (video.path === state.current) renderVideo();
  // Its line under the collection comes from `collection list`: an import or a version change shows there too.
  if (inCollection(video)) await loadCollections();
}

export async function select(path) {
  state.view = 'video';
  state.current = path;
  renderList();
  renderVideo();
}

// The start page, with nothing open: clicking the open video or collection in the sidebar again leads here (user
// request, 2026-10-29: once something was open, there was no way back).
export function showHome() {
  state.view = 'video';
  state.current = null;
  renderList();
  renderVideo();
}

$('add-videos').onclick = async () => addLocalVideos(await window.va.pickVideos());

// Deleting videos (user request, 2026-11-16: one click, several at once): their processing folders with transcript,
// pictures and every summary, their place in collections, and the file itself only when this program downloaded it
// (the CLI's `delete` decides; `show` says which). A video with a task queued or running is left alone.
export async function deleteVideos(paths) {
  const videos = paths.map((path) => state.videos.find((video) => video.path === path) || { path, info: null });
  const busy = videos.filter((video) => videoTask(video));
  if (busy.length) {
    alert(`这些视频还有任务在排队或运行，先停掉再删：\n${busy.map((video) => baseName(video.path)).join('\n')}`);
    return false;
  }
  const mine = videos.filter((video) => video.info?.downloaded);
  const own = videos.length - mine.length;
  const what = [
    `删除 ${videos.length} 个视频的字幕、画面和全部总结版本，并把它们移出所在的合集。`,
    mine.length ? `其中 ${mine.length} 个是本程序下载的，视频文件和旁边的字幕文件也会删掉。` : '',
    own ? `${own} 个是你从本地添加的，视频文件留着不动。` : '',
    '删除后找不回来。',
  ];
  if (!confirm(what.filter(Boolean).join('\n'))) return false;
  const result = await window.va.cliJson(['delete', ...videos.map((video) => video.path), '-o', state.settings.workspace, '--json']);
  if (failed(result)) {
    alert(`没有删完：${result.error}`);
    await Promise.all(state.videos.map(refresh));
    return false;
  }
  const gone = new Set(paths);
  state.videos = state.videos.filter((video) => !gone.has(video.path));
  if (state.current && gone.has(state.current)) state.current = null;
  state.chosen = null;
  await persistList();
  await loadCollections();
  renderList();
  renderVideo();
  return true;
}

$('choose-videos').onclick = () => {
  state.chosen = state.chosen ? null : new Set();
  renderList();
};
$('delete-chosen').onclick = () => state.chosen?.size && deleteVideos([...state.chosen]);
