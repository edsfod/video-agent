// The queue's rules without Electron: pools, one writer per video, no duplicates, order, stop, retry and follow-ups.

const test = require('node:test');
const assert = require('node:assert/strict');
const { TaskQueue, startable } = require('../src/tasks');

const LIMITS = { download: 2, process: 1, summary: 2 };

function queue(options = {}) {
  const started = [];
  const stopped = [];
  const tasks = new TaskQueue({
    start: (task) => started.push(task.id),
    stop: (task) => stopped.push(task.id),
    limits: () => LIMITS,
    ...options,
  });
  const add = (spec) => tasks.add({ title: spec.kind, ...spec }).task;
  const status = () => tasks.list().map((task) => `${task.kind}:${task.status}`);
  return { tasks, add, started, stopped, status };
}

test('each kind waits for a free slot in its own pool', () => {
  const { tasks, add, status } = queue();
  add({ kind: 'download', url: 'https://a' });
  add({ kind: 'download', url: 'https://b' });
  const third = add({ kind: 'download', url: 'https://c' });
  add({ kind: 'process', video: 'C:\\v\\one.mp4' });
  add({ kind: 'process', video: 'C:\\v\\two.mp4' });
  add({ kind: 'frame', video: 'C:\\v\\two.mp4', times: ['5'] });
  assert.deepEqual(status(), [
    'download:running', 'download:running', 'download:queued', 'process:running', 'process:queued', 'frame:running',
  ]);
  tasks.exited(tasks.list()[0].id, 0);
  assert.equal(tasks.get(third.id).status, 'running');
});

test('summaries through DeepSeek run side by side, as other summaries do', () => {
  const spec = (video, route) => ({ kind: 'summary', video, route, agent: route === 'deepseek' ? undefined : route });
  const tasks = [
    { ...spec('C:\\v\\one.mp4', 'deepseek'), status: 'queued' },
    { ...spec('C:\\v\\two.mp4', 'deepseek'), status: 'queued' },
    { ...spec('C:\\v\\three.mp4', 'api'), status: 'queued' },
  ];
  const chosen = startable(tasks, { summary: 2 });
  assert.deepEqual(chosen.map((task) => task.video), ['C:\\v\\one.mp4', 'C:\\v\\two.mp4']);
});

test('processing and summarizing one video never overlap, other videos go ahead', () => {
  const { tasks, add } = queue();
  const processing = add({ kind: 'process', video: 'C:\\v\\one.mp4' });
  const summary = add({ kind: 'summary', video: 'c:/v/ONE.mp4', route: 'api' });
  const other = add({ kind: 'summary', video: 'C:\\v\\two.mp4', route: 'claude' });
  const frame = add({ kind: 'frame', video: 'C:\\v\\one.mp4', times: ['1'] });
  assert.equal(tasks.get(summary.id).status, 'queued');
  assert.equal(tasks.get(other.id).status, 'running', 'a waiting task does not hold back later ones');
  assert.equal(tasks.get(frame.id).status, 'running', 'frames write their own files');
  tasks.exited(processing.id, 0);
  assert.equal(tasks.get(summary.id).status, 'running');
});

test('the same work is not queued twice while it is queued or running', () => {
  const { tasks, add } = queue();
  const first = add({ kind: 'process', video: 'C:\\v\\one.mp4' });
  const again = tasks.add({ kind: 'process', title: 'x', video: 'c:/v/one.mp4' });
  assert.equal(again.added, false);
  assert.equal(again.existing.id, first.id);
  assert.equal(tasks.add({ kind: 'download', title: 'x', url: ' https://a ' }).added, true);
  assert.equal(tasks.add({ kind: 'download', title: 'x', url: 'https://a' }).added, false);
  tasks.exited(first.id, 1);
  assert.equal(tasks.add({ kind: 'process', title: 'x', video: 'C:\\v\\one.mp4' }).added, true, 'allowed again once ended');
});

test('stopping a queued task drops it; stopping a running one ends it as stopped', () => {
  const { tasks, add, stopped } = queue();
  const running = add({ kind: 'process', video: 'C:\\v\\one.mp4' });
  const waiting = add({ kind: 'process', video: 'C:\\v\\two.mp4' });
  tasks.cancel(waiting.id);
  assert.equal(tasks.get(waiting.id).status, 'stopped');
  tasks.cancel(running.id);
  assert.deepEqual(stopped, [running.id]);
  assert.equal(tasks.get(running.id).status, 'running', 'until the process has exited');
  tasks.exited(running.id, 1);
  assert.equal(tasks.get(running.id).status, 'stopped');
});

test('retry queues the same settings as a new task; clearing keeps active tasks', () => {
  const { tasks, add } = queue();
  const failed = add({ kind: 'process', video: 'C:\\v\\one.mp4', interval: 30, bcut: true });
  tasks.exited(failed.id, 1);
  const { task } = tasks.retry(failed.id);
  assert.notEqual(task.id, failed.id);
  assert.equal(task.interval, 30);
  assert.equal(task.bcut, true);
  assert.equal(tasks.retry(task.id), null, 'an active task is not retried');
  tasks.clearFinished();
  assert.deepEqual(tasks.list().map((item) => item.id), [task.id]);
});

test('a video is processed after compressing it, even when compressing failed', () => {
  const { tasks, add } = queue({ followUp: (task) => (task.then ? [{ kind: 'process', title: 'p', video: task.video }] : []) });
  const compress = add({ kind: 'compress', video: 'C:\\d\\a.mp4', then: 'process' });
  tasks.exited(compress.id, 1);
  assert.deepEqual(tasks.list().filter((task) => task.kind === 'process').map((task) => task.video), ['C:\\d\\a.mp4']);
});

test('a download follows up only the videos it saved, not those it found saved already', () => {
  const { tasks, add } = queue({ followUp: (task) => task.fresh.map((video) => ({ kind: 'process', title: 'p', video })) });
  const download = add({ kind: 'download', url: 'https://list' });
  tasks.output(download.id, 'stdout', '{"path": "C:\\\\d\\\\old.mp4", "new": false}\n{"path": "C:\\\\d\\\\new.mp4", "new": true}\n');
  tasks.exited(download.id, 0);
  assert.deepEqual(tasks.get(download.id).paths, ['C:\\d\\old.mp4', 'C:\\d\\new.mp4']);
  assert.deepEqual(tasks.list().filter((task) => task.kind === 'process').map((task) => task.video), ['C:\\d\\new.mp4']);
});

test('a download collects saved paths and is followed up even when another URL failed', () => {
  const { tasks, add } = queue({
    followUp: (task) => task.paths.map((video) => ({ kind: 'process', title: 'p', video })),
  });
  const download = add({ kind: 'download', url: 'https://a' });
  tasks.output(download.id, 'stdout', '{"path": "C:\\\\d\\\\one.mp4"}\n{"pa');
  tasks.output(download.id, 'stdout', 'th": "C:\\\\d\\\\two.mp4"}\nnot json\n');
  tasks.output(download.id, 'stderr', '{"path": "ignored"}\n');
  tasks.exited(download.id, 1);
  assert.deepEqual(tasks.get(download.id).paths, ['C:\\d\\one.mp4', 'C:\\d\\two.mp4']);
  assert.deepEqual(
    tasks.list().filter((task) => task.kind === 'process').map((task) => [task.video, task.status]),
    [['C:\\d\\one.mp4', 'running'], ['C:\\d\\two.mp4', 'queued']],
  );
});

test('a task whose start throws ends as failed and lets the next one start', () => {
  let calls = 0;
  const { tasks, add } = queue({
    start: () => {
      if (++calls === 1) throw new Error('no such program');
    },
  });
  const broken = add({ kind: 'process', video: 'C:\\v\\one.mp4' });
  const next = add({ kind: 'process', video: 'C:\\v\\two.mp4' });
  assert.equal(tasks.get(broken.id).status, 'failed');
  assert.equal(tasks.get(next.id).status, 'running');
});

test('a failed start that frees a slot does not start the next task twice', () => {
  const started = [];
  const tasks = new TaskQueue({
    start: (task) => {
      started.push(task.title);
      if (task.title === 'broken') throw new Error('no such program');
    },
    stop: () => {},
    limits: () => ({ download: 2 }),
  });
  tasks.add({ kind: 'download', title: 'first', url: 'https://a' });
  tasks.exited(tasks.list()[0].id, 0);
  // Both are chosen in one pump; the broken one's failure pumps again before the loop reaches the second.
  tasks.tasks.push(
    { kind: 'download', title: 'broken', url: 'https://b', key: 'b', id: 'b', status: 'queued', output: [], size: 0, lines: '', paths: [] },
    { kind: 'download', title: 'second', url: 'https://c', key: 'c', id: 'c', status: 'queued', output: [], size: 0, lines: '', paths: [] },
  );
  tasks.pump();
  assert.deepEqual(started, ['first', 'broken', 'second']);
});

test('startable is a pure function of the list and the limits', () => {
  const list = [
    { kind: 'process', video: 'a', status: 'running' },
    { kind: 'process', video: 'b', status: 'queued' },
    { kind: 'summary', video: 'b', status: 'queued' },
  ];
  assert.deepEqual(startable(list, { process: 2, summary: 2 }).map((task) => task.kind), ['process']);
  assert.deepEqual(startable(list, { process: 1, summary: 2 }).map((task) => task.kind), ['summary']);
});

test('one collection task at a time per collection, never the same file twice', () => {
  const { tasks, add } = queue();
  const overview = add({ kind: 'collection', collection: 'A', video: '合集:A' });
  const guide = add({ kind: 'collection', collection: 'A', video: '合集:A', guide: true });
  const other = add({ kind: 'collection', collection: 'B', video: '合集:B' });
  assert.equal(tasks.get(overview.id).status, 'running');
  assert.equal(tasks.get(guide.id).status, 'queued');
  assert.equal(tasks.get(other.id).status, 'running');
  assert.equal(tasks.add({ kind: 'collection', title: 'x', collection: 'A', video: '合集:A' }).added, false);
  tasks.exited(overview.id, 0);
  assert.equal(tasks.get(guide.id).status, 'running');
});

test('a download that only found a list ends done, holding the list for the window to ask about', () => {
  const { tasks, add } = queue();
  const download = add({ kind: 'download', url: 'https://space.example/lists/1' });
  tasks.output(download.id, 'stdout', '{"playlist": {"url": "https://space.example/lists/1", "title": "合集·课", "count": 10, "titles": []}}\n');
  tasks.exited(download.id, 1);
  assert.equal(tasks.get(download.id).status, 'done');
  assert.equal(tasks.get(download.id).lists[0].count, 10);
  const again = tasks.retry(download.id).task;
  assert.deepEqual(again.lists, [], 'a retry starts without the old result');
});
