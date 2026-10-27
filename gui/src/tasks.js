// The task queue: every download, processing, summary and frame job the window asks for. Free of Electron, so the
// rules can be tested on their own (test/tasks.test.js); main.js supplies how to start and stop a task.
//
// Which jobs may run at the same time (ARCHITECTURE.md, "Concurrent jobs"), modelled on AutoSlides' download queue:
// - Nothing is refused for being busy: a task waits in the queue until it may start.
// - Each kind has its own pool (`limits`): downloads, processing (FFmpeg uses the whole CPU) and summaries; frame
//   captures take seconds and have no limit.
// - Processing and summarizing change the same files in a video's folder, so at most one of them runs per video. The
//   CLI enforces the same rule with a lock; the queue keeps the window from running into it, and also covers the Agent
//   routes, which write 总结.md without the CLI.
// - The same work queued twice (same kind and target, still queued or running) is not added again.
// - Tasks start in the order they were added; one that has to wait does not hold back later ones that may run.

const DEFAULT_LIMITS = { download: 3, process: 1, summary: 2 };
// Collection tasks write the collection's own files; their `video` is "合集:<name>", so one runs per collection.
const EXCLUSIVE = new Set(['process', 'summary', 'collection']);
const ACTIVE = new Set(['queued', 'running']);
const OUTPUT_LIMIT = 512 * 1024; // characters of output kept per task for the window; the log file has all of it

function videoKey(video) {
  return String(video).replace(/\//g, '\\').toLowerCase();
}

// What makes two tasks the same work.
function workKey(spec) {
  if (spec.kind === 'download') return `download|${spec.url.trim()}`;
  if (spec.kind === 'frame') return `frame|${videoKey(spec.video)}|${spec.times.join(' ')}`;
  if (spec.kind === 'collection') return `collection|${spec.collection}|${spec.guide ? 'guide' : 'overview'}`;
  return `${spec.kind}|${videoKey(spec.video)}`;
}

// The queued tasks that may start now, given those already running.
function startable(tasks, limits = DEFAULT_LIMITS) {
  const counts = {};
  const busy = new Set();
  const take = (task) => {
    counts[task.kind] = (counts[task.kind] || 0) + 1;
    if (EXCLUSIVE.has(task.kind)) busy.add(videoKey(task.video));
  };
  tasks.filter((task) => task.status === 'running').forEach(take);
  const chosen = [];
  for (const task of tasks) {
    if (task.status !== 'queued') continue;
    if ((counts[task.kind] || 0) >= (limits[task.kind] ?? Infinity)) continue;
    if (EXCLUSIVE.has(task.kind) && busy.has(videoKey(task.video))) continue;
    take(task);
    chosen.push(task);
  }
  return chosen;
}

let counter = 0;
const newId = () => `task-${Date.now().toString(36)}-${(++counter).toString(36)}`;

// start(task): starts the job; it reports back through output() and exited().
// stop(task): stops a running job. changed(): the list or a status changed.
// followUp(task): tasks to add after a task succeeds (a download's "then process").
class TaskQueue {
  constructor({ start, stop, changed = () => {}, limits = () => DEFAULT_LIMITS, followUp = () => [] }) {
    Object.assign(this, { start, stop, changed, limits, followUp });
    this.tasks = [];
  }

  // spec: { kind, title, video?, url?, times?, ... }. Returns { added: true, task } or { added: false, existing }.
  add(spec) {
    const key = workKey(spec);
    const existing = this.tasks.find((task) => task.key === key && ACTIVE.has(task.status));
    if (existing) return { added: false, existing: this.summary(existing) };
    const task = { ...spec, id: newId(), key, status: 'queued', added: Date.now(), output: [], size: 0, lines: '' };
    task.paths = [];
    this.tasks.push(task);
    this.pump();
    return { added: true, task: this.summary(task) };
  }

  pump() {
    for (const task of startable(this.tasks, this.limits())) {
      if (task.status !== 'queued') continue; // a failed start below pumps again and may have started it
      task.status = 'running';
      task.started = Date.now();
      try {
        this.start(task);
      } catch (error) {
        this.output(task.id, 'stderr', `${error.message}\n`);
        this.finish(task, -1);
      }
    }
    this.changed();
  }

  output(id, stream, text) {
    const task = this.get(id);
    if (!task) return;
    task.output.push([stream, text]);
    task.size += text.length;
    while (task.size > OUTPUT_LIMIT && task.output.length > 1) task.size -= task.output.shift()[1].length;
    // A download prints one JSON object per saved file on stdout.
    if (task.kind === 'download' && stream === 'stdout') {
      const lines = (task.lines + text).split(/\r?\n/);
      task.lines = lines.pop();
      for (const line of lines) {
        try {
          const path = JSON.parse(line).path;
          if (path) task.paths.push(path);
        } catch {
          // not a result line
        }
      }
    }
  }

  exited(id, code) {
    const task = this.get(id);
    if (task && task.status === 'running') this.finish(task, code);
  }

  finish(task, code) {
    task.code = code;
    task.ended = Date.now();
    task.status = task.stopping ? 'stopped' : code === 0 ? 'done' : 'failed';
    // A download that saved files is followed up even if another URL in it failed.
    const follow = task.status !== 'stopped' && (code === 0 || task.paths.length) ? this.followUp(task) : [];
    for (const spec of follow) this.add(spec);
    this.pump();
  }

  // Queued: dropped from the queue. Running: stopped; it ends as 'stopped' when the process exits.
  cancel(id) {
    const task = this.get(id);
    if (!task) return;
    if (task.status === 'queued') {
      task.status = 'stopped';
      task.ended = Date.now();
      this.pump();
    } else if (task.status === 'running') {
      task.stopping = true;
      this.stop(task);
    }
  }

  cancelAll() {
    for (const task of this.tasks.filter((item) => ACTIVE.has(item.status))) this.cancel(task.id);
  }

  // Queues a finished task again as a new task, with the same settings.
  retry(id) {
    const task = this.get(id);
    if (!task || ACTIVE.has(task.status)) return null;
    const { id: _, key, status, added, started, ended, code, output, size, lines, paths, stopping, ...spec } = task;
    return this.add(spec);
  }

  clearFinished() {
    this.tasks = this.tasks.filter((task) => ACTIVE.has(task.status));
    this.changed();
  }

  get(id) {
    return this.tasks.find((task) => task.id === id);
  }

  active() {
    return this.tasks.filter((task) => ACTIVE.has(task.status));
  }

  // What the window and the tray see; the output is fetched separately.
  summary(task) {
    const { output, size, lines, run, ...rest } = task;
    return rest;
  }

  list() {
    return this.tasks.map((task) => this.summary(task));
  }
}

module.exports = { TaskQueue, startable, workKey, videoKey, DEFAULT_LIMITS };
