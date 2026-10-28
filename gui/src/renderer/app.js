// Window logic. Every action runs the Video Agent CLI (or an Agent CLI) through window.va; nothing here touches media.

const $ = (id) => document.getElementById(id);
const state = {
  settings: null,
  env: null,
  videos: [], // { path, info, error }
  current: null,
  tab: 'process',
  route: 'claude',
  tasks: [], // the queue in the main process (tasks.js), without output
  shown: null, // { id, buffer, loading }: the task whose output the panel shows
  collections: [], // `video-agent collection list`: each with its videos and their states
  view: 'video', // or 'collection', with state.collection its name
  collection: null,
  doc: 'overview', // the collection file shown: overview (合集总结) or guide (学习提纲)
  version: null, // { video, file }: a summary version shown instead of the current one
  tools: null, // `video-agent tools`: where FFmpeg, yt-dlp and AutoSlides Extractor were found (null: not found)
  term: null,
  bilibili: { loggedIn: false }, // { loggedIn, name? }
};
let ptyCounter = 0;

// ---------- helpers ----------

function fileUrl(file) {
  const parts = file.replace(/\\/g, '/').split('/');
  return 'file:///' + [parts[0], ...parts.slice(1).map(encodeURIComponent)].join('/');
}

function clock(seconds) {
  const total = Math.round(seconds || 0);
  const pad = (n) => String(n).padStart(2, '0');
  return `${pad(Math.floor(total / 3600))}:${pad(Math.floor((total % 3600) / 60))}:${pad(total % 60)}`;
}

function baseName(file) {
  return file.split(/[\\/]/).pop();
}

function joinPath(folder, relative) {
  return folder.replace(/[\\/]+$/, '') + '\\' + relative.replace(/\//g, '\\');
}

function current() {
  return state.videos.find((video) => video.path === state.current) || null;
}

function element(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  Object.assign(node, props);
  for (const child of [].concat(children)) node.append(child);
  return node;
}

// ---------- tasks ----------
// The queue runs in the main process, so it survives a reload of this page and keeps going in the tray. This page adds
// tasks, shows them, and refreshes a video when one of its tasks ends.

const STATUS = { queued: '排队中', running: '运行中', done: '完成', failed: '未完成', stopped: '已停止' };
const ACTIVE = new Set(['queued', 'running']);
const sameVideo = (a, b) => !!a && !!b && a.replace(/\//g, '\\').toLowerCase() === b.replace(/\//g, '\\').toLowerCase();

function logAppend(text) {
  const pre = $('log-text');
  const atBottom = pre.scrollHeight - pre.scrollTop - pre.clientHeight < 30;
  pre.textContent += text;
  if (atBottom) pre.scrollTop = pre.scrollHeight;
}

// Adds a task, or shows the same one already in the queue. Resolves to true when a new task was added.
async function addTask(spec) {
  const result = await window.va.addTask(spec);
  const task = result.added ? result.task : result.existing;
  await showTask(task.id);
  note(result.added ? '' : '同样的任务已经在队列里了。');
  return result.added;
}

function note(text) {
  $('task-note').textContent = text;
  clearTimeout(note.timer);
  if (text) note.timer = setTimeout(() => ($('task-note').textContent = ''), 6000);
}

// Shows a task's output so far, then follows it live.
async function showTask(id) {
  $('log').hidden = false;
  state.shown = { id, buffer: '', loading: true };
  $('log-text').textContent = '';
  renderTasks();
  const chunks = await window.va.taskOutput(id);
  if (state.shown?.id !== id) return;
  const task = state.tasks.find((item) => item.id === id);
  // Output sent before this reply is in `chunks`; live output arrives after it, so nothing is lost or doubled.
  for (const [stream, text] of chunks) taskOutput(task, stream, text);
  state.shown.loading = false;
  if (task && !ACTIVE.has(task.status)) taskEnd(task);
}

function taskOutput(task, stream, text) {
  if (!task) return;
  if (stream !== 'stdout') return logAppend(text);
  const lines = (state.shown.buffer + text).split(/\r?\n/);
  state.shown.buffer = lines.pop();
  for (const line of lines) if (line.trim()) taskLine(task, line);
}

// stdout of each kind: result JSON for process and download, the Agent's event stream for summaries.
function taskLine(task, line) {
  if (task.kind === 'summary' && task.route === 'claude') return claudeLine(line);
  if (task.kind === 'summary' && task.route === 'codex') return codexLine(line);
  let result;
  try {
    result = JSON.parse(line);
  } catch {
    return logAppend(line + '\n');
  }
  if (task.kind === 'download' && result.path) logAppend(`已保存：${result.path}\n`);
  else if (result.error) logAppend(`错误：${result.error}\n`);
  else if (result.transcript_error) logAppend(`字幕没有拿到：${result.transcript_error}\n`);
}

function taskEnd(task) {
  if (state.shown.buffer.trim()) taskLine(task, state.shown.buffer);
  state.shown.buffer = '';
  const end = { done: '完成', stopped: '已停止' }[task.status] || `结束（退出码 ${task.code}）`;
  logAppend(`\n${end}\n`);
}

window.va.onJobOutput(({ id, stream, text }) => {
  if (state.shown?.id !== id || state.shown.loading) return;
  taskOutput(state.tasks.find((task) => task.id === id), stream, text);
});

window.va.onTasks((tasks) => {
  const before = new Map(state.tasks.map((task) => [task.id, task.status]));
  state.tasks = tasks;
  for (const task of tasks) {
    if (!ACTIVE.has(before.get(task.id)) || ACTIVE.has(task.status)) continue;
    if (state.shown?.id === task.id && !state.shown.loading) taskEnd(task);
    taskFinished(task);
  }
  renderTasks();
  renderList();
  if ($('settings').open) renderWorkspaceLock();
});

async function taskFinished(task) {
  loadCollections(); // a member's state or a collection file may have changed
  if (task.kind === 'download') {
    if (task.paths.length && $('download-url').value.trim() === task.url) $('download-url').value = '';
    if (task.paths.length) await addVideos(task.paths, { show: !task.update && !task.collection });
    if (!task.paths.length && task.lists?.length) askPlaylist(task.lists[0], task.then);
    return;
  }
  const video = state.videos.find((item) => sameVideo(item.path, task.video));
  if (video) await refresh(video);
}

function videoTask(video) {
  const tasks = state.tasks.filter((task) => ACTIVE.has(task.status) && sameVideo(task.video, video.path));
  return tasks.find((task) => task.status === 'running') || tasks[0];
}

function renderTasks() {
  const tasks = state.tasks;
  const active = tasks.filter((task) => ACTIVE.has(task.status)).length;
  $('open-tasks').textContent = active ? `任务（${active}）` : '任务';
  const shown = tasks.find((task) => task.id === state.shown?.id);
  $('log-title').textContent = shown ? `${shown.title} · ${STATUS[shown.status]}` : '任务';
  $('cancel-job').hidden = !shown || !ACTIVE.has(shown.status);
  $('clear-tasks').disabled = tasks.length === active;
  $('task-list').replaceChildren(
    ...[...tasks].reverse().map((task) => {
      const item = element('div', { className: `task-item ${task.status}` + (task.id === state.shown?.id ? ' active' : '') }, [
        element('span', { className: 'name', textContent: task.title, title: task.title }),
        element('span', { className: `badge ${task.status}`, textContent: STATUS[task.status] }),
      ]);
      if (!ACTIVE.has(task.status) && task.status !== 'done') {
        const retry = element('button', { className: 'ghost small', textContent: '重试', title: '用同样的设置再排一次' });
        retry.onclick = async (event) => {
          event.stopPropagation();
          const result = await window.va.retryTask(task.id);
          if (result) showTask((result.task || result.existing).id);
        };
        item.append(retry);
      }
      item.onclick = () => showTask(task.id);
      return item;
    }),
  );
}

$('cancel-job').onclick = () => state.shown && window.va.cancelTask(state.shown.id);
$('clear-tasks').onclick = () => window.va.clearTasks();
$('close-log').onclick = () => ($('log').hidden = true);
$('open-tasks').onclick = () => {
  if (!$('log').hidden) return ($('log').hidden = true);
  const latest = state.tasks.at(-1);
  if (latest) showTask(state.shown?.id || latest.id);
  else ($('log').hidden = false), renderTasks();
};

// ---------- video list ----------

// `show: false` adds them without opening the last one, for downloads that fill a collection in the background.
async function addVideos(paths, { show = true } = {}) {
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
async function addLocalVideos(paths) {
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
  for (const video of fresh.filter((entry) => entry.info.subtitles)) await process(video, false);
  const bare = fresh.filter((entry) => !entry.info.subtitles);
  if (!bare.length) return;
  $('nosubs-list').replaceChildren(...bare.map((video) => element('li', { textContent: baseName(video.path) })));
  $('nosubs-dialog').returnValue = '';
  $('nosubs-dialog').showModal();
  await new Promise((resolve) => $('nosubs-dialog').addEventListener('close', resolve, { once: true }));
  const choice = $('nosubs-dialog').returnValue;
  if (choice === 'bcut' || choice === 'pictures') for (const video of bare) await process(video, choice === 'bcut');
}

async function persistList() {
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
const isVideo = (path, video) => [video?.path, video?.info?.video].some((own) => sameVideo(own, path));
// A video in a collection is listed under the collection in the sidebar, not here (user decision, 2026-10-28).
const inCollection = (video) => state.collections.some((item) => item.videos.some((member) => isVideo(member.video, video)));

function renderList() {
  const list = $('video-list');
  const shown = state.videos.filter((video) => !inCollection(video));
  list.replaceChildren(
    ...shown.map((video) => {
      const active = state.view === 'video' && video.path === state.current;
      const item = element('div', { className: 'video-item' + (active ? ' active' : '') }, [
        element('span', { className: 'name', textContent: baseName(video.path), title: video.path }),
        badge(video),
      ]);
      item.onclick = () => select(video.path);
      return item;
    }),
  );
  if (!shown.length && state.videos.length) {
    list.append(element('p', { className: 'muted small-text list-note', textContent: '视频都在上面的合集里。' }));
  }
  renderCollectionList();
}

async function refresh(video) {
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

async function select(path) {
  state.view = 'video';
  state.current = path;
  renderList();
  renderVideo();
}

// ---------- video view ----------

function renderVideo() {
  $('collection').hidden = state.view !== 'collection';
  if (state.view === 'collection') {
    $('empty').hidden = true;
    $('video').hidden = true;
    return renderCollection();
  }
  const video = current();
  $('empty').hidden = !!video;
  $('video').hidden = !video;
  if (!video) return;
  $('video-name').textContent = baseName(video.path);
  $('video-path').textContent = video.path;
  $('reveal-folder').disabled = !video.info?.processed;
  // A collection's video is not in the 视频 list, so there is nothing to take it out of; its page leads back instead.
  $('remove-video').hidden = inCollection(video);
  const holder = state.collections.find((item) => item.videos.some((member) => isVideo(member.video, video)));
  const member = holder?.videos.find((entry) => isVideo(entry.video, video));
  $('video-collection').hidden = !holder;
  if (holder) {
    $('video-collection').textContent = `← ${holder.name} · 第 ${member.index} 集`;
    $('video-collection').onclick = () => openCollection(holder.name);
  }
  renderTab();
}

function renderTab() {
  for (const button of document.querySelectorAll('#video .tabs button')) {
    button.classList.toggle('active', button.dataset.tab === state.tab);
  }
  for (const panel of document.querySelectorAll('#video .panel')) {
    panel.hidden = panel.dataset.panel !== state.tab;
    if (!panel.hidden) panel.scrollTop = 0;
  }
  const video = current();
  if (!video) return;
  ({ process: renderProcess, transcript: renderTranscript, frames: renderFrames, summary: renderSummary, terminal: renderTerminal })[
    state.tab
  ](video);
}

for (const button of document.querySelectorAll('#video .tabs button')) {
  button.onclick = () => {
    state.tab = button.dataset.tab;
    renderTab();
  };
}

function renderProcess(video) {
  $('opt-interval').value = state.settings.frameInterval;
  $('opt-bcut').checked = state.settings.bcut !== false;
  // The external extractor is offered only where the CLI finds it (state.tools is null until `tools` answered).
  const extractor = !state.tools || state.tools.slide_extractor;
  $('opt-slides').disabled = !extractor;
  if (!extractor) $('opt-slides').checked = false;
  $('opt-slides-note').textContent = extractor
    ? '屏幕页总会截取，写总结不需要它；要去重更细、导出课件时再勾。耗时较长。'
    : '没有找到 AutoSlides Extractor。屏幕页照样会截取；需要它时安装后重新打开本程序。';
  $('opt-max-frames').value = state.settings.maxFrames || '';
  const info = video.info;
  const facts = [];
  if (video.error) facts.push(['错误', video.error]);
  if (info) {
    facts.push(['时长', clock(info.duration_s)]);
    const manifest = info.manifest;
    if (manifest) {
      const transcript = manifest.transcript;
      const sources = {
        'bcut-remote': '必剪转录',
        unavailable: '没有字幕',
        'no-audio-or-subtitles': '无音频',
        'existing-output': '沿用上次的字幕',
        'existing-output-preserved': '沿用上次的字幕',
      };
      const source = sources[transcript.source] || subtitleSource(transcript.source);
      facts.push(['字幕', `${transcript.segments} 段 · ${source}`, '', transcript.source.replace(/^sidecar:/, '')]);
      if (transcript.error) facts.push(['字幕问题', transcript.error]);
      if (manifest.layout) facts.push(['布局', LAYOUT_TEXT[manifest.layout.kind] + (manifest.layout.given ? '（手动指定）' : '')]);
      if (manifest.screen_pages) facts.push(['屏幕页', `${manifest.screen_pages.length} 页`]);
      facts.push(['整幅画面', `${manifest.representative_frames.length} 张，补截 ${info.extra_frames.length} 张`]);
      const slides = manifest.slide_extraction;
      if (slides.imported) facts.push(['课件', `${slides.slides.length} 张`, '', slides.imported]);
      else if (slides.enabled) facts.push(['PPT', `${slides.slides.length} 张`]);
      facts.push(['总结', info.summary ? '已生成' : '还没有']);
      facts.push(['处理结果', info.folder, 'wide']);
    }
    $('process-state').textContent = info.processed ? '已处理过；再次处理会重新抽取画面，已有字幕保留。' : '';
    $('run-process').textContent = info.processed ? '重新处理' : '开始处理';
  }
  renderLayout(video);
  $('facts').replaceChildren(
    ...facts.map(([label, value, size, hint]) =>
      element('div', { className: 'fact' + (size ? ' ' + size : ''), title: hint || '' }, [
        element('div', { className: 'label', textContent: label }),
        element('div', { className: 'value', textContent: value }),
      ]),
    ),
  );
}

// A subtitle file beside the video is named <video>.<language>.srt by yt-dlp, or <video>.srt when the user put it there.
const LANGUAGES = { 'ai-zh': 'B 站 AI 字幕', zh: '中文字幕', 'zh-hans': '中文字幕', 'zh-cn': '中文字幕', 'zh-hant': '繁体中文字幕', en: '英文字幕' };
function subtitleSource(source) {
  if (source.startsWith('embedded:')) return `内嵌字幕（${source.slice(9) || '未标语言'}）`;
  if (source.startsWith('file:')) return `导入的字幕（${source.slice(5)}）`;
  if (!source.startsWith('sidecar:')) return source;
  const language = /\.([A-Za-z-]+)\.(srt|vtt|ass)$/i.exec(source.slice(8))?.[1]?.toLowerCase();
  return language ? LANGUAGES[language] || `字幕文件（${language}）` : '同名字幕文件';
}

// ---------- layout ----------
// The CLI finds the screen region; when it is wrong the user drags the right one on the layout picture.

const LAYOUT_TEXT = { screen: '整个画面是屏幕', split: '屏幕和摄像头分开', inset: '屏幕里嵌着摄像头', camera: '只有摄像头，没有屏幕页' };

function renderLayout(video) {
  const found = video.info?.manifest?.layout;
  $('layout-card').hidden = !found?.picture;
  if (!found?.picture) return;
  const [width, height] = found.size;
  const where = found.screen && found.kind !== 'camera' ? `屏幕区域 ${found.screen[2]}×${found.screen[3]}，位于 ${found.screen[0]},${found.screen[1]}` : '';
  $('layout-text').textContent = `${LAYOUT_TEXT[found.kind]}。${where}（画面 ${width}×${height}）。绿框是屏幕区域，红框是摄像头。认错了就在图上拖出屏幕那块，再重新处理。`;
  $('layout-image').src = fileUrl(joinPath(video.info.folder, found.picture));
  $('layout-box').hidden = true;
  $('layout-region').value = found.screen && found.kind !== 'camera' ? found.screen.join(',') : '';
}

// Dragging works in the picture's own pixels, which are the video's.
(() => {
  const image = $('layout-image');
  let start = null;
  const point = (event) => {
    const box = image.getBoundingClientRect();
    const scale = image.naturalWidth / box.width;
    const clamp = (value, limit) => Math.max(0, Math.min(limit, Math.round(value * scale)));
    return { x: clamp(event.clientX - box.left, image.naturalWidth), y: clamp(event.clientY - box.top, image.naturalHeight), scale };
  };
  const draw = (a, b) => {
    const [x, y, w, h] = [Math.min(a.x, b.x), Math.min(a.y, b.y), Math.abs(a.x - b.x), Math.abs(a.y - b.y)];
    Object.assign($('layout-box').style, { left: `${x / a.scale}px`, top: `${y / a.scale}px`, width: `${w / a.scale}px`, height: `${h / a.scale}px` });
    $('layout-box').hidden = false;
    return [x, y, w, h];
  };
  image.addEventListener('mousedown', (event) => {
    event.preventDefault();
    start = point(event);
  });
  window.addEventListener('mousemove', (event) => start && draw(start, point(event)));
  window.addEventListener('mouseup', (event) => {
    if (!start) return;
    const [x, y, w, h] = draw(start, point(event));
    start = null;
    if (w > 8 && h > 8) $('layout-region').value = [x, y, w, h].join(',');
  });
})();

$('layout-apply').onclick = () => {
  const region = $('layout-region').value.replace(/\s+/g, '');
  if (!/^\d+,\d+,\d+,\d+$/.test(region)) return alert('屏幕区域要写成 x,y,宽,高 四个整数，或者在图上拖出来。');
  startProcess({ screenRegion: region });
};

$('run-process').onclick = () => startProcess();

async function startProcess(extra = {}) {
  const video = current();
  const interval = Number($('opt-interval').value) || 60;
  const maxFrames = Number($('opt-max-frames').value) || null; // empty: as many as the video has
  state.settings = await window.va.saveSettings({ frameInterval: interval, maxFrames, bcut: $('opt-bcut').checked });
  await addTask({
    kind: 'process',
    title: `处理：${baseName(video.path)}`,
    video: video.path,
    interval,
    maxFrames,
    bcut: $('opt-bcut').checked,
    slides: $('opt-slides').checked,
    ...extra,
  });
}
// This program's downloads go to <workspace>\下载; any other video is the user's own file, which is replaced only with
// their agreement: the setting, or a confirmation here.
const downloaded = (video) => video.path.toLowerCase().startsWith(joinPath(state.settings.workspace, '下载').toLowerCase() + '\\');
$('run-compress').onclick = async () => {
  const video = current();
  if (!video) return;
  const asked = '压缩会用 AV1 重新编码这个视频，然后用压缩后的文件替换你电脑上的原视频（原文件不保留）。分辨率不变，替换前会核对时长。继续吗？';
  if (!downloaded(video) && !state.settings.compressLocal && !confirm(asked)) return;
  await addTask({ kind: 'compress', title: `压缩：${baseName(video.path)}`, video: video.path });
};
$('opt-bcut').onchange = async () => (state.settings = await window.va.saveSettings({ bcut: $('opt-bcut').checked }));

// A subtitle file of any name, such as one the teacher shared, replaces the transcript; processing runs with it.
$('import-subtitles').onclick = async () => {
  const video = current();
  const file = await window.va.pickFile('选择字幕文件', [{ name: '字幕', extensions: ['srt', 'vtt'] }]);
  if (!video || !file) return;
  await addTask({
    kind: 'process',
    title: `导入字幕：${baseName(video.path)}`,
    video: video.path,
    interval: state.settings.frameInterval,
    maxFrames: state.settings.maxFrames,
    subtitles: file,
  });
};

async function renderTranscript(video) {
  const box = $('transcript');
  const pairs = video.info?.corrections || [];
  $('corrections').hidden = !video.info?.transcript;
  $('corrections-count').textContent = pairs.length ? `（${pairs.length} 条）` : '';
  $('corrections-list').replaceChildren(
    ...pairs.map(([wrong, right]) => {
      const undo = element('button', { className: 'ghost small', textContent: '撤销', title: '去掉这条改正' });
      undo.onclick = () => runFix(video, ['--remove', wrong]);
      return element('span', { className: 'correction' }, [element('span', { textContent: `${wrong} → ${right}` }), undo]);
    }),
  );
  // With a cleaned transcript, show it unless the original is asked for.
  const cleaned = pairs.length > 0 && video.info.transcript !== video.info.transcript_original;
  $('transcript-original-label').hidden = !cleaned;
  if (!video.info?.transcript) {
    const why = video.info?.processed
      ? '没有找到字幕：视频旁边没有同名字幕文件，视频里也没有字幕轨。可以点「导入字幕…」选一个字幕文件，或在「处理」里勾上必剪转录（会上传音轨）再处理一次。'
      : '还没有字幕。处理这个视频时会读进同名的字幕文件；字幕文件名字不同时，点「导入字幕…」。';
    box.replaceChildren(element('p', { className: 'muted', textContent: why }));
    $('transcript-count').textContent = '';
    return;
  }
  const file = cleaned && $('transcript-original').checked ? video.info.transcript_original : video.info.transcript;
  const text = await window.va.read(file);
  const filter = $('transcript-filter').value.trim().toLowerCase();
  const lines = (text || '').split(/\r?\n/).filter(Boolean);
  const shown = lines.filter((line) => !filter || line.toLowerCase().includes(filter));
  $('transcript-count').textContent = filter ? `${shown.length} / ${lines.length} 行` : `${lines.length} 行`;
  box.replaceChildren(
    ...shown.map((line) => {
      const match = line.match(/^\[(\d\d:\d\d:\d\d)\]\s?(.*)$/);
      return element('div', { className: 'line' }, [
        element('time', { textContent: match ? match[1] : '' }),
        element('span', { textContent: match ? match[2] : line }),
      ]);
    }),
  );
}
$('transcript-filter').oninput = () => renderTranscript(current());
$('transcript-original').onchange = () => renderTranscript(current());

// Corrections go through the CLI (video-agent fix), which keeps the original and rebuilds the cleaned transcript.
async function runFix(video, args) {
  const result = await window.va.cliJson(['fix', video.path, '-o', state.settings.workspace, '--json', ...args]);
  if (result.error) {
    $('corrections-state').textContent = `没有改成：${result.error}`;
    return;
  }
  const missing = result.unmatched.length ? `；没找到：${result.unmatched.join('、')}` : '';
  $('corrections-state').textContent = `改动了 ${result.changed_lines} 行${missing}`;
  await refresh(video);
}

$('corrections-form').onsubmit = async (event) => {
  event.preventDefault();
  const wrong = $('correction-wrong').value.trim();
  const right = $('correction-right').value.trim();
  if (!wrong || !right || wrong === right) return;
  await runFix(current(), ['--replace', wrong, right]);
  $('correction-wrong').value = '';
  $('correction-right').value = '';
};

function frameCard(item) {
  const card = element('div', { className: 'frame' + (item.extra ? ' extra' : '') }, [
    element('img', { src: fileUrl(item.file), alt: '', loading: 'lazy' }),
    element('div', { textContent: clock(item.time) }),
  ]);
  card.onclick = () => showImage(item.file, clock(item.time));
  return card;
}

function renderFrames(video) {
  const box = $('frames');
  const manifest = video.info?.manifest;
  // Slides taken from a folder (AutoSlides' or one chosen) stand for the screen pages wherever they have times.
  const slides = (manifest?.slide_extraction?.slides || []).filter((slide) => slide.time_s !== null);
  const pages = slides.length ? slides : manifest?.screen_pages || [];
  $('pages-title').hidden = !pages.length;
  $('pages-title').textContent = slides.length ? `课件（${pages.length}）` : `屏幕页（${pages.length}）`;
  $('pages').replaceChildren(
    ...pages.map((page) => frameCard({ time: page.time_s, file: joinPath(video.info.folder, page.path) })),
  );
  $('frames-title').hidden = !manifest;
  if (!manifest) {
    box.replaceChildren(element('p', { className: 'muted', textContent: '还没有画面。先在「处理」里处理这个视频。' }));
    return;
  }
  const items = manifest.representative_frames.map((frame) => ({
    time: frame.time_s,
    file: joinPath(video.info.folder, frame.path),
    extra: false,
  }));
  for (const file of video.info.extra_frames) {
    const match = baseName(file).match(/frame-(\d\d)-(\d\d)-(\d\d)\.jpg$/);
    if (match) items.push({ time: +match[1] * 3600 + +match[2] * 60 + +match[3], file, extra: true });
  }
  items.sort((a, b) => a.time - b.time);
  $('frames-title').textContent = `整幅画面（${items.length}）`;
  box.replaceChildren(...items.map(frameCard));
}

// A folder of slide images, such as AutoSlides' or exported from the PPT; processing runs again with it.
$('import-slides').onclick = async () => {
  const video = current();
  const folder = await window.va.pickFolder('选择课件图片所在的文件夹');
  if (!video || !folder) return;
  await addTask({
    kind: 'process',
    title: `导入课件：${baseName(video.path)}`,
    video: video.path,
    interval: state.settings.frameInterval,
    maxFrames: state.settings.maxFrames,
    slidesFolder: folder,
  });
};

$('frame-form').onsubmit = (event) => {
  event.preventDefault();
  const video = current();
  const times = $('frame-times').value.trim().split(/[\s,，]+/).filter(Boolean);
  if (!times.length || !video.info?.processed) return;
  addTask({ kind: 'frame', title: `补截画面：${times.join(' ')}`, video: video.path, times });
  $('frame-times').value = '';
};

function showImage(file, caption) {
  $('lightbox-image').src = fileUrl(file);
  $('lightbox-caption').textContent = caption || file;
  $('lightbox').showModal();
}
$('lightbox').onclick = () => $('lightbox').close();

// ---------- summary ----------

const ROUTE_NOTES = {
  claude: '在后台运行 Claude Code，按 video-agent skill 写总结，会按需补截画面。使用你的 Claude 订阅。',
  codex: '在后台运行 Codex，按同一份 skill 写总结。使用你的 Codex 订阅。',
  api: '用设置里的模型 API 写总结（字幕和画面会发给该服务商）。支持工具调用的模型会按需补截画面。',
  copy: '把规则、模板和字幕材料复制到剪贴板，贴进任何聊天 AI。要连画面一起给，用「导出 zip」；不收 zip、文件数有上限的（如 DeepSeek 网页版最多 50 个），用「导出文件夹」，屏幕页会拼成总图凑进上限。写好后用「导入总结」存回来，画面链接照样能点开。',
};

// Each other agent the settings show is a route of its own, keyed as in the settings (pi, hermes, dsh, custom).
const otherRoute = (route) => state.env.others.find((agent) => agent.key === route);
// The route's name in task titles; another agent goes by the name the settings give it.
const routeName = (route) => ({ api: '模型 API', claude: 'Claude Code', codex: 'Codex' })[route] || otherRoute(route)?.name;
const routeMissing = (route) =>
  (route === 'claude' && !state.env.claude) || (route === 'codex' && !state.env.codex) || otherRoute(route)?.found === false;
const routeNote = (route) =>
  ROUTE_NOTES[route] ||
  (otherRoute(route)
    ? `在后台运行 ${otherRoute(route).name}，按同一份 skill 写总结。它以你的身份运行命令，不限于工作区。`
    : '还没有其他 Agent：在「设置」→「其他 Agent」里勾上 pi、Hermes Agent、DeepSeek Harness，或填你自己的命令。');

// With no other agent, a 其他 Agent route still shows, so it can be found, and says where to add one.
function otherRouteLabels() {
  const others = state.env.others.length ? state.env.others : [{ key: 'other', name: '其他 Agent' }];
  return others.map(({ key, name }) =>
    element('label', { className: 'route-agent' }, [element('input', { type: 'radio', name: 'route', value: key }), ` ${name}`]),
  );
}

function renderRoutes() {
  for (const label of document.querySelectorAll('#routes .route-agent')) label.remove();
  $('routes').querySelector('input[value=api]').parentElement.before(...otherRouteLabels());
  if (!document.querySelector(`input[name=route][value="${state.route}"]`)) state.route = 'api';
  for (const input of document.querySelectorAll('input[name=route]')) {
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
}

async function renderSummary(video) {
  renderRoutes();
  const article = $('summary');
  const info = video.info;
  $('run-summary').disabled = !info?.processed || state.route === 'other';
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
  const list = found.error ? { current: null, versions: [] } : found;
  if (state.version?.video !== video.path || !list.versions.some((entry) => entry.file === state.version.file)) {
    state.version = null;
  }
  renderVersions(list);
  const shown = state.version ? list.versions.find((entry) => entry.file === state.version.file).path : info.summary;
  const text = await window.va.read(shown);
  article.innerHTML = DOMPurify.sanitize(marked.parse(text || ''));
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

const versionArgs = (...args) => ['versions', current().path, '-o', state.settings.workspace, ...args];
$('summary-version-pick').onchange = () => {
  const file = $('summary-version-pick').value;
  state.version = file ? { video: current().path, file } : null;
  renderSummary(current());
};
$('summary-version-use').onclick = async () => {
  const result = await window.va.cliText(versionArgs('--use', state.version.file));
  if (result.code !== 0) return alert(`没有换成：${(result.err || result.out).trim()}`);
  state.version = null;
  summaryState('已换成这个版本；原来的总结留作一个版本。');
  await refresh(current());
};
$('summary-version-delete').onclick = async () => {
  if (!confirm('删除这个版本？删除后找不回来。')) return;
  const result = await window.va.cliText(versionArgs('--delete', state.version.file));
  if (result.code !== 0) return alert(`没有删除：${(result.err || result.out).trim()}`);
  state.version = null;
  await refresh(current());
};
// Electron has no window.prompt(), so the note is edited in a dialog of its own, starting from the note it has.
$('summary-version-note').onclick = () => {
  const list = state.versionList;
  const shown = state.version ? list?.versions.find((entry) => entry.file === state.version.file) : list?.current;
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

$('open-summary').onclick = () => current()?.info?.summary && window.va.open(current().info.summary);

$('run-summary').onclick = async () => {
  const video = current();
  const info = video.info;
  const request = $('summary-request').value.trim();
  if (state.route === 'copy') return copyMaterial();
  const name = routeName(state.route);
  // A summary there already stays current; the new one is kept as a version to compare and choose.
  if (info.summary) summaryState('已经有总结：新写的会另存为一个版本，原来的不动。');
  addTask({
    kind: 'summary',
    title: `总结（${name}）：${baseName(video.path)}`,
    route: state.route,
    agent: state.route === 'api' ? undefined : state.route,
    video: video.path,
    folder: info.folder,
    request,
    overwrite: false,
  });
};

// Claude Code stream-json: show text and tool calls; skip the rest.
function claudeLine(line) {
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
function codexLine(line) {
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
const packArgs = (video) => ['pack', video.path, '-o', state.settings.workspace, '--request', $('summary-request').value.trim()];

function summaryState(text) {
  $('summary-state').textContent = text;
  clearTimeout(summaryState.timer);
  summaryState.timer = setTimeout(() => ($('summary-state').textContent = ''), 10000);
}

async function copyMaterial() {
  const result = await window.va.cliText(packArgs(current()));
  if (result.code !== 0) return alert(`没有复制：${result.err || result.out}`);
  await window.va.copy(result.out);
  summaryState(`已复制 ${result.out.length} 个字符。画面没有一起复制；要连画面一起给，用「导出 zip」。`);
}

$('export-zip').onclick = async () => {
  const video = current();
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
  const video = current();
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

let importFile = null;
let importTarget = null; // null for the current video, or { collection, guide }

$('import-summary').onclick = () => {
  if (busyWriting(current())) return alert('这个视频正在处理或总结，等任务结束再导入。');
  importTarget = null;
  openImport();
};

function openImport() {
  importFile = null;
  $('import-text').value = '';
  $('import-file-name').textContent = '';
  $('import-note').value = '';
  $('import-current').checked = false;
  // Choosing only matters with something there already; the first text becomes current anyway.
  const item = importTarget && state.collections.find((entry) => entry.name === importTarget.collection);
  const exists = importTarget ? (importTarget.guide ? item?.guide : item?.overview) : current()?.info?.summary;
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
  const video = current();
  const args = ['summarize', video.path, '-o', state.settings.workspace, '--import', importFile || '-', '--source', '网页 AI'];
  const note = $('import-note').value.trim();
  if (note) args.push('--note', note);
  const asCurrent = !video.info.summary || $('import-current').checked;
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

// ---------- collections ----------
// A collection is an ordered set of related videos with an overview and a study guide (ARCHITECTURE.md,
// "Collections"); everything goes through `video-agent collection`, `summarize --collection` and `pack --collection`.

const collectionArgs = (...args) => ['collection', ...args, '-o', state.settings.workspace];
const currentCollection = () => state.collections.find((item) => item.name === state.collection) || null;

async function loadCollections() {
  const result = await window.va.cliJson(collectionArgs('list'));
  state.collections = Array.isArray(result) ? result : [];
  renderList(); // also the collections
  if (state.view === 'collection') renderVideo();
}

// Each collection, and under it its videos when it is open: on its page, playing one of its videos, or opened with ▸.
// The sidebar lists collections only; their videos are opened from the collection's page, where there is room
// (user request, 2026-10-28). A collection holding the video shown is marked as well.
function renderCollectionList() {
  $('collection-list').replaceChildren(
    ...state.collections.map((item) => {
      const holdsCurrent = state.view === 'video' && item.videos.some((member) => isVideo(member.video, current()));
      const active = (state.view === 'collection' && item.name === state.collection) || holdsCurrent;
      const busy = item.videos.filter((member) => videoTask({ path: member.video })).length; // queued or running
      const row = element('div', { className: 'video-item collection-item' + (active ? ' active' : '') }, [
        element('span', { className: 'name', textContent: item.name, title: item.folder }),
        element('span', { className: 'badge', textContent: `${item.videos.length} 集` + (busy ? ` · ${busy} 个任务` : '') }),
      ]);
      row.onclick = () => openCollection(item.name);
      return row;
    }),
  );
}

// A collection's video opens on its own page; it is kept in the window's list of known videos, hidden from 视频.
function openMember(path) {
  const known = state.videos.find((video) => isVideo(path, video));
  return known ? select(known.path) : addVideos([path]);
}

function openCollection(name) {
  state.view = 'collection';
  state.collection = name;
  renderList();
  renderCollectionList();
  renderVideo();
}

async function collectionCommand(args, done = '') {
  const result = await window.va.cliJson(collectionArgs(...args));
  $('collection-state').textContent = result.error ? `没有成功：${result.error}` : done;
  await loadCollections();
  return !result.error;
}

function memberBadges(member) {
  const badges = [];
  const add = (text, kind = '') => badges.push(element('span', { className: `badge ${kind}`, textContent: text }));
  if (member.skipped) add(`已跳过：${member.skipped}`);
  else if (member.summary) add('已总结', 'done');
  else add(member.processed ? '已处理' : '未处理');
  if (member.maybe_empty && !member.skipped) add('可能是空的', 'busy');
  return badges;
}

async function renderCollection() {
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
  for (const button of document.querySelectorAll('.doc-tabs button')) button.classList.toggle('active', button.dataset.doc === state.doc);
  const file = state.doc === 'guide' ? item.guide : item.overview;
  const article = $('collection-doc');
  if (!file) {
    article.replaceChildren(element('p', { className: 'placeholder', textContent: state.doc === 'guide' ? '还没有学习提纲。' : '还没有合集总结。' }));
    return;
  }
  article.innerHTML = DOMPurify.sanitize(marked.parse((await window.va.read(file)) || ''));
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

for (const button of document.querySelectorAll('.doc-tabs button')) {
  button.onclick = () => {
    state.doc = button.dataset.doc;
    renderCollection();
  };
}

$('collection-route').onchange = () => renderCollection();
$('collection-folder').onclick = () => currentCollection() && window.va.open(currentCollection().folder);
$('collection-delete').onclick = async () => {
  const item = currentCollection();
  if (!item || !confirm(`删除合集「${item.name}」吗？各个视频和它们的总结都会保留，只删合集自己的文件（合集总结、学习提纲、共用术语）。`)) return;
  state.view = 'video';
  await collectionCommand(['delete', item.name]);
  renderVideo();
};
// ---------- following a list ----------

const CHECK_EVERY_MS = 6 * 3600 * 1000;

function renderSource(item) {
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
    url: item.source.url, // for the Bilibili login and so the same list is not checked twice at once
    update: item.name,
    then: state.settings.processAfterDownload !== false ? 'process' : undefined,
  });
}

$('collection-check').onclick = () => checkSource(currentCollection()).then(() => renderVideo());
$('collection-auto').onchange = () =>
  collectionCommand(['follow', currentCollection().name, $('collection-auto').checked ? '--auto' : '--no-auto']);
$('collection-unfollow').onclick = () => collectionCommand(['unfollow', currentCollection().name], '不再跟踪这个列表');
$('collection-follow-form').onsubmit = async (event) => {
  event.preventDefault();
  const url = $('collection-follow-url').value.trim();
  if (!url) return;
  if (await collectionCommand(['follow', currentCollection().name, url], '已跟踪；点「检查新视频」下载还没有的')) {
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
  if (path) collectionCommand(['add', currentCollection().name, path]);
};
// Local files go into the video list too, so they can be processed from there.
$('collection-add-files').onclick = async () => {
  const paths = await window.va.pickVideos();
  if (!paths?.length) return;
  await addLocalVideos(paths);
  await collectionCommand(['add', currentCollection().name, ...paths]);
};
$('collection-process-all').onclick = async () => {
  for (const member of currentCollection().videos.filter((entry) => !entry.skipped && !entry.processed)) {
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
  for (const member of currentCollection().videos.filter((entry) => !entry.skipped && entry.processed && !entry.summary)) {
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
  const item = currentCollection();
  const route = $('collection-route').value;
  const request = $('collection-request').value.trim();
  const file = guide ? '学习提纲' : '合集总结';
  if (route === 'copy') {
    const args = ['pack', '--collection', item.name, '-o', state.settings.workspace, '--request', request];
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
  importTarget = { collection: currentCollection().name, guide: state.doc === 'guide' };
  openImport();
};

async function importCollection(text) {
  const { collection, guide } = importTarget;
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
  if (await collectionCommand(['terms', currentCollection().name, '--replace', wrong, right], `已改正 ${wrong} → ${right}，各集的整理版字幕已更新`)) {
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
$('join-collection').onclick = () => current() && openCollectionDialog(current().path);
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
function askSkip(member) {
  skipping = member;
  $('skip-dialog-video').textContent = member.name;
  $('skip-dialog-reason').value = member.maybe_empty ? '几乎没有内容' : '';
  $('skip-dialog').showModal();
}
$('skip-dialog').addEventListener('close', () => {
  if ($('skip-dialog').returnValue !== 'save' || !skipping) return;
  const reason = $('skip-dialog-reason').value.trim() || '跳过';
  collectionCommand(['skip', currentCollection().name, skipping.video, '--reason', reason]);
});

// ---------- terminal ----------

function renderTerminal(video) {
  const select = $('shell-choice');
  if (!select.options.length) {
    for (const item of state.env.shells) select.append(element('option', { value: item.id, textContent: item.label }));
    select.value = state.settings.shell || state.env.shells[0]?.id || '';
  }
  if (!state.term) newTerminal(video);
  else requestAnimationFrame(() => state.term.fit.fit());
}

async function newTerminal(video) {
  if (state.term) {
    window.va.ptyKill(state.term.id);
    state.term.xterm.dispose();
  }
  const xterm = new Terminal({
    fontFamily: "'Cascadia Mono', Consolas, monospace",
    fontSize: 13,
    cursorBlink: true,
    theme: { background: '#1b1a18', foreground: '#ecebe6' },
  });
  const fit = new FitAddon.FitAddon();
  xterm.loadAddon(fit);
  xterm.open($('terminal'));
  fit.fit();
  const id = `pty-${++ptyCounter}`;
  state.term = { id, xterm, fit };
  xterm.onData((data) => window.va.ptyWrite(id, data));
  xterm.onResize(({ cols, rows }) => window.va.ptyResize(id, cols, rows));
  const shellId = $('shell-choice').value;
  state.settings = await window.va.saveSettings({ shell: shellId });
  const cwd = video?.info?.processed ? video.info.folder : state.settings.workspace;
  await window.va.ptyStart({ id, shellId, cwd, cols: xterm.cols, rows: xterm.rows });
  xterm.focus();
}

window.va.onPtyData(({ id, data }) => state.term?.id === id && state.term.xterm.write(data));
window.va.onPtyExit(({ id }) => state.term?.id === id && state.term.xterm.write('\r\n[已退出，点「新建终端」重新打开]\r\n'));
$('new-terminal').onclick = () => newTerminal(current());
$('shell-choice').onchange = () => newTerminal(current());
new ResizeObserver(() => state.term && state.tab === 'terminal' && state.term.fit.fit()).observe($('terminal'));

// ---------- sidebar actions ----------

$('add-videos').onclick = async () => addLocalVideos(await window.va.pickVideos());

// ---------- Bilibili login (subtitles are shown only to logged-in accounts) ----------

const isBilibili = (url) => /(^|[/.])(bilibili\.com|b23\.tv)([/:?#]|$)/i.test(url);

function renderBilibili() {
  const { loggedIn, name } = state.bilibili;
  $('bili-status').textContent = loggedIn ? `已登录${name ? `：${name}` : ''}` : '没有登录';
  $('bili-login').textContent = loggedIn ? '重新登录' : '登录';
  $('bili-logout').hidden = !loggedIn;
  $('download-hint').hidden = loggedIn || !isBilibili($('download-url').value.trim());
}

async function bilibiliLogin() {
  state.bilibili = await window.va.bilibiliLogin();
  renderBilibili();
}

$('bili-login').onclick = bilibiliLogin;
$('download-login').onclick = (event) => (event.preventDefault(), bilibiliLogin());
$('bili-logout').onclick = async () => {
  state.bilibili = await window.va.bilibiliLogout();
  renderBilibili();
};
$('download-url').oninput = renderBilibili;

$('download-form').onsubmit = (event) => {
  event.preventDefault();
  const url = $('download-url').value.trim();
  if (!url) return;
  const then = $('download-then-process').checked ? 'process' : undefined;
  addTask({ kind: 'download', title: `下载：${url}`, url, then });
};
// A link that stands for a list (a season, a series, a channel) is not downloaded until the user says so.
let pendingList = null;
function askPlaylist(found, then) {
  pendingList = { url: found.url, then };
  const title = found.title || found.url;
  $('playlist-dialog-info').textContent = `这个链接是一个列表：「${title}」，共 ${found.count} 个视频。`;
  const shown = found.titles.filter(Boolean);
  $('playlist-dialog-titles').replaceChildren(
    ...shown.map((name) => element('li', { textContent: name })),
    ...(found.count > shown.length && shown.length ? [element('li', { textContent: '…' })] : []),
  );
  $('playlist-dialog-titles').hidden = !shown.length;
  $('playlist-dialog-name').value = title.replace(/^合集[·・:：]\s*/, '');
  $('playlist-dialog-join').checked = true;
  $('playlist-dialog-follow').checked = true;
  $('playlist-dialog-auto').checked = false;
  renderPlaylistDialog();
  $('playlist-dialog').showModal();
}
// Following needs a collection to keep the list in; checking on its own needs following.
function renderPlaylistDialog() {
  const joined = $('playlist-dialog-join').checked;
  $('playlist-dialog-name-label').hidden = !joined;
  $('playlist-dialog-follow-label').hidden = !joined;
  $('playlist-dialog-auto-label').hidden = !joined || !$('playlist-dialog-follow').checked;
}
$('playlist-dialog-join').onchange = renderPlaylistDialog;
$('playlist-dialog-follow').onchange = renderPlaylistDialog;
$('playlist-dialog').addEventListener('close', async () => {
  if ($('playlist-dialog').returnValue !== 'save' || !pendingList) return;
  const { url, then } = pendingList;
  pendingList = null;
  const collection = $('playlist-dialog-join').checked ? $('playlist-dialog-name').value.trim() : '';
  const follow = Boolean(collection) && $('playlist-dialog-follow').checked;
  const auto = follow && $('playlist-dialog-auto').checked;
  await addTask({
    kind: 'download', title: `下载列表：${collection || url}`, url, then, playlist: true,
    collection: collection || undefined, follow, auto,
  });
  if (added && $('download-url').value.trim() === url) $('download-url').value = '';
});

$('download-then-process').onchange = () =>
  window.va.saveSettings({ processAfterDownload: $('download-then-process').checked }).then((next) => (state.settings = next));

$('reveal-video').onclick = () => window.va.reveal(current().path);
$('reveal-folder').onclick = () => current()?.info?.folder && window.va.open(current().info.folder);
$('remove-video').onclick = async () => {
  state.videos = state.videos.filter((video) => video.path !== state.current);
  state.current = state.videos[0]?.path || null;
  await persistList();
  renderList();
  renderVideo();
};

document.addEventListener('dragover', (event) => event.preventDefault());
document.addEventListener('drop', (event) => {
  event.preventDefault();
  const paths = [...event.dataTransfer.files].map((file) => window.va.droppedPath(file)).filter(Boolean);
  if (paths.length) addLocalVideos(paths);
});

// ---------- settings ----------

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
  for (const kind of ['download', 'process', 'summary']) $(`set-limit-${kind}`).value = state.settings.limits[kind];
  renderWorkspaceLock();
  $('set-update-mirror').value = state.settings.updateMirror || '';
  renderUpdate(await window.va.updateState());
  renderRules();
  const cli = state.env.bundled ? '安装程序自带的 video-agent' : state.env.cli.join(' ');
  $('env-info').textContent =
    `正在用的命令：${cli} · Claude Code：${state.env.claude ? '已找到' : '没有找到'} · Codex：${state.env.codex ? '已找到' : '没有找到'}` +
    state.env.others.map((agent) => ` · ${agent.name}：${agent.found ? '已找到' : '没有找到'}`).join('');
  $('install-claude').disabled = !state.env.claude;
  $('install-codex').disabled = !state.env.codex;
  $('plugin-output').hidden = true;
  const config = await window.va.cliJson(['config', '--json']);
  if (config.error) {
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
  'set-theme', 'set-workspace', 'set-cli', 'set-close-to-tray', 'set-compress-downloads', 'set-compress-local', 'set-check-updates', 'set-update-mirror', 'set-limit-download',
  'set-limit-process', 'set-limit-summary', 'set-provider', 'set-model', 'set-base-url', 'set-key',
];
const settingsValues = () =>
  JSON.stringify([SETTINGS_FIELDS.map((id) => ($(id).type === 'checkbox' ? $(id).checked : $(id).value)), agentRowsValue()]);
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
let agentRowsShown = '';
function renderAgentRows() {
  const saved = Object.fromEntries(state.env.others.map((agent) => [agent.key, agent.command]));
  const rows = [...Object.entries(state.env.agents), ['custom', { name: '自定义命令', command: '' }]].map(([key, preset]) => {
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
const agentRowsValue = () =>
  [...document.querySelectorAll('#set-agents input[data-agent]')].filter((box) => box.checked).map((box) => {
    const command = document.querySelector(`#set-agents input[data-agent-command="${box.dataset.agent}"]`).value.trim();
    return { key: box.dataset.agent, command: command === state.env.agents[box.dataset.agent]?.command ? '' : command };
  });
$('settings').addEventListener('close', () => {
  if ($('settings').returnValue !== 'save') window.va.previewTheme(state.settings.theme || 'system');
  $('settings-unsaved').hidden = true;
  $('discard-settings').textContent = '取消';
});
// Read-only windows close on a click outside too.
for (const id of ['skill-dialog', 'logs']) $(id).addEventListener('click', (event) => event.target === $(id) && $(id).close());

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

// Tasks keep the workspace they were added with; changing it under them would hide their results.
function renderWorkspaceLock() {
  const active = state.tasks.filter((task) => ACTIVE.has(task.status)).length;
  $('pick-workspace').disabled = active > 0;
  $('workspace-lock').hidden = active === 0;
}

// ---------- summary rules ----------
// The rules every summary route follows; the CLI keeps the user's copy (video-agent template --edit).

async function renderRules() {
  const info = await window.va.cliJson(['template', '--info']);
  if (info.error) return ($('rules-status').textContent = `读取不到：${info.error}`);
  $('rules-status').textContent = !info.customized
    ? '正在用默认规则。'
    : info.outdated
      ? '正在用你改过的版本。新版的默认规则有改动：打开对比，把需要的改动合并进你的版本，再点「已合并」。'
      : '正在用你改过的版本。';
  $('rules-reset').hidden = !info.customized;
  $('rules-compare').hidden = $('rules-accept').hidden = !info.outdated;
}

async function rulesAction(flag) {
  const info = await window.va.cliJson(['template', flag]);
  if (info.error) alert(`没有成功：${info.error}`);
  await renderRules();
  return info;
}

$('rules-edit').onclick = async () => {
  const info = await rulesAction('--edit');
  if (info.path) window.va.open(info.path);
};
$('rules-compare').onclick = async () => {
  const info = await rulesAction('--info');
  if (info.default) window.va.open(info.default);
  if (info.path) window.va.open(info.path);
};
$('rules-accept').onclick = () => rulesAction('--accept');
$('rules-reset').onclick = () => confirm('删除你改过的版本，回到默认规则吗？') && rulesAction('--reset');
$('skill-view').onclick = async () => {
  $('skill-text').innerHTML = DOMPurify.sanitize(marked.parse(await window.va.readSkill()));
  $('skill-dialog').showModal();
};
$('close-skill').onclick = () => $('skill-dialog').close();

$('pick-workspace').onclick = async () => {
  const folder = await window.va.pickFolder('选择工作区');
  if (folder) $('set-workspace').value = folder;
};

$('set-provider').onchange = async () => {
  const config = await window.va.cliJson(['config', '--json', '--provider', $('set-provider').value]);
  if (!config.error) {
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
    updateMirror: $('set-update-mirror').value.trim(),
    limits: Object.fromEntries(
      ['download', 'process', 'summary'].map((kind) => [kind, Math.min(8, Math.max(1, Number($(`set-limit-${kind}`).value) || 1))]),
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

// ---------- updates ----------

const RELEASES_PAGE = 'https://github.com/edsfod/video-agent/releases';
const megabytes = (bytes) => (bytes / 1048576).toFixed(1);

// 1, 0 or -1 as version a is newer than, the same as or older than b (plain x.y.z numbers).
function newer(a, b) {
  const [x, y] = [a, b].map((version) => version.split('.').map(Number));
  for (let i = 0; i < 3; i++) if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) > (y[i] || 0) ? 1 : -1;
  return 0;
}

// 今天 14:33, 昨天 09:05, or 10月27日 14:33.
function when(iso) {
  const date = new Date(iso);
  const time = date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  const days = Math.round((new Date().setHours(0, 0, 0, 0) - new Date(iso).setHours(0, 0, 0, 0)) / 86400000);
  return days === 0 ? `今天 ${time}` : days === 1 ? `昨天 ${time}` : `${date.getMonth() + 1}月${date.getDate()}日 ${time}`;
}

function renderUpdate(update) {
  const current = update.current;
  const last = update.lastCheck;
  // What that check found, against the version running now (it may have been installed since).
  const order = last ? newer(last.version, current) : 0;
  const found = order > 0 ? `，当时发现新版本 ${last.version}` : order === 0 ? '，没有更新的版本' : '';
  const lastText = last ? `上次检查更新：${when(last.at)}（经 ${last.source}）${found}。` : '还没有检查过更新。';
  const text = {
    idle: update.message ? `当前版本 ${current}。${update.message}` : `当前版本 ${current}。${lastText}`,
    checking: '正在检查更新…',
    latest: `当前版本 ${current}。${lastText}`,
    available: `有新版本 ${update.version}，当前是 ${current}。`,
    downloading: `正在经 ${update.source} 下载 ${update.version}：${Math.floor(update.percent || 0)}%` +
      (update.total ? `（${megabytes(update.transferred)} / ${megabytes(update.total)} MB）` : ''),
    downloaded: `${update.version} 已下载并通过校验，点“重启并安装”完成更新；设置和工作区都会保留。`,
    error: '检查更新没有成功，可以稍后再试，或打开发布页手动下载。',
  }[update.status];
  const failure = update.status !== 'idle' && update.message ? `\n${update.message}` : '';
  $('update-status').textContent = text + failure;
  $('update-check').disabled = ['checking', 'downloading', 'downloaded'].includes(update.status);
  $('update-download').hidden = update.status !== 'available';
  $('update-install').hidden = update.status !== 'downloaded';
  $('update-progress').hidden = update.status !== 'downloading';
  $('update-progress').value = update.percent || 0;
  const notes = ['available', 'downloading', 'downloaded'].includes(update.status) && update.notes;
  $('update-notes').hidden = !notes;
  if (notes) $('update-notes').innerHTML = DOMPurify.sanitize(marked.parse(notes));
  for (const link of $('update-notes').querySelectorAll('a[href]')) {
    link.onclick = (event) => (event.preventDefault(), window.va.external(link.href));
  }
  $('open-settings').classList.toggle('has-update', ['available', 'downloading', 'downloaded'].includes(update.status));
  $('open-settings').title = $('open-settings').classList.contains('has-update') ? `有新版本 ${update.version}` : '';
}

window.va.onUpdateState(renderUpdate);
$('update-check').onclick = () => window.va.checkUpdate();
$('update-download').onclick = () => window.va.downloadUpdate();
$('update-releases').onclick = () => window.va.external(RELEASES_PAGE);
$('update-install').onclick = async () => {
  const result = await window.va.installUpdate(false);
  if (result.running && confirm(`还有 ${result.running} 个任务在运行，安装更新会停止它们。现在安装吗？`)) {
    await window.va.installUpdate(true);
  }
};

// ---------- logs ----------

$('open-logs').onclick = async () => {
  const entries = await window.va.logs();
  const list = $('log-list');
  list.replaceChildren(
    ...entries.map((entry) => {
      const failed = entry.exit !== null && entry.exit !== 0;
      const status = entry.exit === null ? '未结束或被中断' : entry.exit === 0 ? `完成 · ${entry.seconds} 秒` : `退出码 ${entry.exit}`;
      const item = element('div', { className: 'log-entry' }, [
        element('div', { textContent: entry.title || baseName(entry.file) }),
        element('div', {
          className: 'meta' + (failed ? ' fail' : ''),
          textContent: `${new Date(entry.started).toLocaleString('zh-CN')} · ${status}`,
        }),
      ]);
      item.onclick = async () => {
        for (const other of list.children) other.classList.remove('active');
        item.classList.add('active');
        // The first and last lines are metadata for the list; show the command instead.
        const body = (await window.va.readLog(entry.file)).split('\n').filter((line) => !line.startsWith('# {')).join('\n');
        $('log-view').textContent = `$ ${(entry.command || []).join(' ')}\n\n${body.trim()}\n`;
      };
      return item;
    }),
  );
  $('log-view').textContent = entries.length ? '选择左边的一条记录查看完整输出。' : '还没有任务记录。';
  $('logs').showModal();
  list.firstElementChild?.click();
};
$('close-logs').onclick = () => $('logs').close();
$('open-log-folder').onclick = () => window.va.openLogs();

window.addEventListener('error', (event) => window.va.logError(event.error?.stack || event.message));
window.addEventListener('unhandledrejection', (event) => window.va.logError(event.reason?.stack || event.reason));
window.va.onTrayAddVideos(async () => addLocalVideos(await window.va.pickVideos()));

// ---------- start ----------

async function init() {
  state.settings = await window.va.settings();
  state.env = await window.va.env();
  renderUpdate(await window.va.updateState());
  window.va.bilibiliStatus().then((status) => ((state.bilibili = status), renderBilibili()));
  state.route = state.env.claude ? 'claude' : state.env.codex ? 'codex' : 'api';
  state.videos = state.settings.videos.map((path) => ({ path, info: null }));
  state.tasks = await window.va.tasks();
  $('download-then-process').checked = state.settings.processAfterDownload !== false; // on unless turned off
  renderTasks();
  renderList();
  if (state.videos.length) select(state.videos[0].path);
  else renderVideo();
  loadCollections();
  window.va.cliJson(['tools', '--json']).then((found) => {
    state.tools = found.error ? null : found;
    if (state.view === 'video') renderVideo();
  });
  await Promise.all(state.videos.map(refresh));
}

// Used by `electron . --screenshot=<file> --select=<n> --tab=<name>`.
window.__screenshot = async ({ select: index, tab }) => {
  await ready;
  if (index !== undefined && state.videos[Number(index)]) await select(state.videos[Number(index)].path);
  if (tab === 'logs' || tab === 'settings') return $(`open-${tab}`).click();
  if (tab) {
    state.tab = tab;
    renderTab();
  }
};

const ready = init();
