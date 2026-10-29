// A video's page: its header and tabs, and the 处理, 字幕 and 画面 tabs.

import { COMPRESSION, openCollection, renderCollection } from './collections.js';
import { $, $$, baseName, clock, current, element, failed, fileUrl, joinPath, pageVideo, state } from './state.js';
import { renderSummary } from './summary.js';
import { addTask } from './task-panel.js';
import { renderTerminal } from './terminal.js';
import { inCollection, isVideo, refresh } from './video-list.js';

export function renderVideo() {
  $('collection').hidden = state.view !== 'collection';
  if (state.view === 'collection') {
    $('empty').hidden = true;
    $('video').hidden = true;
    return renderCollection();
  }
  const video = current();
  $('empty').hidden = !!video;
  $('video').hidden = !video;
  $('empty-pick').hidden = !(state.videos.length || state.collections.length);
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
    $('video-collection').textContent = `← ${holder.name} · 第 ${member?.index} 集`;
    $('video-collection').onclick = () => openCollection(holder.name);
  }
  renderTab();
}

export function renderTab() {
  for (const button of $$('#video .tabs button')) {
    button.classList.toggle('active', button.dataset.tab === state.tab);
  }
  for (const panel of $$('#video .panel')) {
    panel.hidden = panel.dataset.panel !== state.tab;
    if (!panel.hidden) panel.scrollTop = 0;
  }
  const video = current();
  if (!video) return;
  ({ process: renderProcess, transcript: renderTranscript, frames: renderFrames, summary: renderSummary, terminal: renderTerminal })[
    state.tab
  ](video);
}

for (const button of $$('#video .tabs button')) {
  button.onclick = () => {
    state.tab = button.dataset.tab;
    renderTab();
  };
}

function renderProcess(video) {
  $('opt-interval').value = state.settings.frameInterval;
  $('opt-bcut').checked = state.settings.bcut !== false;
  // AutoSlides Extractor finds the screen pages where the CLI finds it, unless turned off here (user decision,
  // 2026-10-29); state.tools is null until `tools` answered.
  const extractor = !state.tools || state.tools.slide_extractor;
  $('opt-slides').disabled = !extractor;
  $('opt-slides').checked = !!extractor && state.settings.extractor !== false;
  $('opt-slides-note').textContent = extractor
    ? '已安装：屏幕页由它来找，讲者翻得快的页也不会漏；取消勾选就用本程序自己的规则。'
    : '没有找到 AutoSlides Extractor，屏幕页用本程序自己的规则找；装上后重新打开本程序就会用它。';
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
  // A video that needs no compressing says so on the button instead of offering it.
  const done = COMPRESSION[info?.compression];
  $('run-compress').disabled = !!done;
  $('run-compress').textContent = done ? done[0] : '压缩这个视频…';
  $('run-compress').title = done ? done[1] : '用 AV1 重新编码并替换这个视频文件，分辨率不变';
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

// ---------- the 处理, 字幕 and 画面 tabs ----------
// The CLI finds the screen region; when it is wrong the user drags the right one on the layout picture.

const LAYOUT_TEXT = {
  screen: '整个画面是屏幕',
  split: '屏幕和摄像头分开',
  inset: '屏幕里嵌着摄像头',
  projected: '摄像机拍的投影或屏幕',
  camera: '只有摄像头，屏幕页是画面里停住的图表和截图',
};

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
  const video = pageVideo();
  const interval = Number($('opt-interval').value) || 60;
  const maxFrames = Number($('opt-max-frames').value) || null; // empty: as many as the video has
  const extractor = $('opt-slides').disabled ? state.settings.extractor : $('opt-slides').checked;
  state.settings = await window.va.saveSettings({ frameInterval: interval, maxFrames, bcut: $('opt-bcut').checked, extractor });
  await addTask({
    kind: 'process',
    title: `处理：${baseName(video.path)}`,
    video: video.path,
    interval,
    maxFrames,
    bcut: $('opt-bcut').checked,
    ...extra,
  });
}
// This program's downloads go to <workspace>\下载, or to the folder a followed list saves to; any other video is the
// user's own file, which is replaced only with their agreement: the setting, or a confirmation here.
export const downloaded = (video) =>
  [joinPath(state.settings.workspace, '下载'), ...state.collections.flatMap((item) => (item.source ? [item.source.folder] : []))].some(
    (folder) => video.path.toLowerCase().startsWith(folder.replace(/[\\/]+$/, '').toLowerCase() + '\\'),
  );
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
  if (failed(result)) {
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
  const video = pageVideo();
  const times = $('frame-times').value.trim().split(/[\s,，]+/).filter(Boolean);
  if (!times.length || !video.info?.processed) return;
  addTask({ kind: 'frame', title: `补截画面：${times.join(' ')}`, video: video.path, times });
  $('frame-times').value = '';
};

export function showImage(file, caption) {
  $('lightbox-image').src = fileUrl(file);
  $('lightbox-caption').textContent = caption || file;
  $('lightbox').showModal();
}
$('lightbox').onclick = () => $('lightbox').close();
