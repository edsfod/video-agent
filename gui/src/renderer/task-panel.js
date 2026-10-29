// The task panel at the bottom: the queue in the main process (tasks.js), each task's output, and adding tasks.

import { loadCollections } from './collections.js';
import { renderWorkspaceLock } from './settings.js';
import { askPlaylist } from './site-accounts.js';
import { $, element, state } from './state.js';
import { claudeLine, codexLine, effortFor, modelFor, modelTakes } from './summary.js';
import { STANDARD_TEMPLATE, chosenTemplate } from './templates.js';
import { addVideos, refresh, renderList } from './video-list.js';

// The queue runs in the main process, so it survives a reload of this page and keeps going in the tray. This page adds
// tasks, shows them, and refreshes a video when one of its tasks ends.

const STATUS = { queued: '排队中', running: '运行中', done: '完成', failed: '未完成', stopped: '已停止' };
export const ACTIVE = new Set(['queued', 'running']);
export const sameVideo = (a, b) => !!a && !!b && a.replace(/\//g, '\\').toLowerCase() === b.replace(/\//g, '\\').toLowerCase();

export function logAppend(text) {
  const pre = $('log-text');
  const atBottom = pre.scrollHeight - pre.scrollTop - pre.clientHeight < 30;
  pre.textContent += text;
  if (atBottom) pre.scrollTop = pre.scrollHeight;
}

// Adds a task, or shows the same one already in the queue. Resolves to true when a new task was added.
export async function addTask(spec) {
  // A summary runs with the template chosen on the summary page, and the model chosen there for its route, if any.
  if (['summary', 'collection'].includes(spec.kind) && spec.route) {
    const model = modelTakes(spec.route) ? modelFor(spec.route) : '';
    const effort = modelTakes(spec.route) ? effortFor(spec.route) : '';
    const template = chosenTemplate();
    spec = { ...spec, model: model || undefined, effort: effort || undefined, template };
    const chosen = [model, effort, template === STANDARD_TEMPLATE ? '' : template].filter(Boolean);
    if (chosen.length) spec.title = spec.title.replace(/^(总结|合集总结|学习提纲)（([^）]+)）/, `$1（$2 · ${chosen.join(' · ')}）`);
  }
  const result = await window.va.addTask(spec);
  const task = result.added ? result.task : result.existing;
  await showTask(task.id);
  note(result.added ? '' : '同样的任务已经在队列里了。');
  return result.added;
}

let noteTimer;
function note(text) {
  $('task-note').textContent = text;
  clearTimeout(noteTimer);
  if (text) noteTimer = setTimeout(() => ($('task-note').textContent = ''), 6000);
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
  if (!task || !state.shown) return;
  if (stream !== 'stdout') return logAppend(text);
  const lines = (state.shown.buffer + text).split(/\r?\n/);
  state.shown.buffer = lines.pop() || '';
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
  if (!state.shown) return;
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
    if (state.shown && state.shown.id === task.id && !state.shown.loading) taskEnd(task);
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

export function videoTask(video) {
  const tasks = state.tasks.filter((task) => ACTIVE.has(task.status) && sameVideo(task.video, video.path));
  return tasks.find((task) => task.status === 'running') || tasks[0];
}

export function renderTasks() {
  const tasks = state.tasks;
  const active = tasks.filter((task) => ACTIVE.has(task.status)).length;
  $('open-tasks').textContent = active ? `任务（${active}）` : '任务';
  const shown = tasks.find((task) => task.id === state.shown?.id);
  $('log-title').textContent = shown ? `${shown.title} · ${STATUS[shown.status]}` : '任务';
  $('cancel-job').hidden = !shown || !ACTIVE.has(shown.status);
  $('clear-tasks').disabled = tasks.length === active;
  // Ticked tasks that have ended since are no longer ticked.
  for (const id of state.picked) if (!tasks.some((task) => task.id === id && ACTIVE.has(task.status))) state.picked.delete(id);
  $('stop-picked').hidden = !state.picked.size;
  $('stop-picked').textContent = `停止所选（${state.picked.size}）`;
  $('stop-all').disabled = !active;
  $('task-list').replaceChildren(
    ...[...tasks].reverse().map((task) => {
      const item = element('div', { className: `task-item ${task.status}` + (task.id === state.shown?.id ? ' active' : '') }, [
        element('span', { className: 'name', textContent: task.title, title: task.title }),
        element('span', { className: `badge ${task.status}`, textContent: STATUS[task.status] }),
      ]);
      if (ACTIVE.has(task.status)) {
        const pick = element('input', { type: 'checkbox', className: 'pick', checked: state.picked.has(task.id), title: '选中后可以一起停止' });
        pick.onclick = (event) => event.stopPropagation();
        pick.onchange = () => {
          if (pick.checked) state.picked.add(task.id);
          else state.picked.delete(task.id);
          renderTasks();
        };
        item.prepend(pick);
      }
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
$('stop-picked').onclick = () => {
  window.va.cancelTask([...state.picked]);
  state.picked.clear();
  renderTasks();
};
$('stop-all').onclick = () => {
  const active = state.tasks.filter((task) => ACTIVE.has(task.status));
  const running = active.filter((task) => task.status === 'running').length;
  if (!active.length || !confirm(`停止全部 ${active.length} 个任务？正在运行的 ${running} 个会中断（压缩停下时原视频不变），排队的移出队列。`)) return;
  window.va.cancelTask(active.map((task) => task.id));
};
$('clear-tasks').onclick = () => window.va.clearTasks();
$('close-log').onclick = () => ($('log').hidden = true);
$('open-tasks').onclick = () => {
  if (!$('log').hidden) return ($('log').hidden = true);
  const latest = state.tasks.at(-1);
  if (latest) showTask(state.shown?.id || latest.id);
  else ($('log').hidden = false), renderTasks();
};
