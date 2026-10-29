// Running the queue's tasks (tasks.js holds the queue): each kind's CLI command line, Agent routes, cookies for a
// download, and what follows a finished task.

const { app } = require('electron');
const { spawn, spawnSync } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
const shared = require('./shared');
const { send } = shared;
const accounts = require('./accounts');
const chatRounds = require('./chat-rounds');
const models = require('./models');
const { TaskQueue, DEFAULT_LIMITS } = require('./tasks');
const { cookiesDir, loadSettings } = require('./settings');
const { AGENTS, childEnv, cliCommand, launch, otherAgents, pluginRoot } = require('./programs');
const { updateTray } = require('./window');

/**
 * @param {string} id
 * @param {string} command
 * @param {string[]} args
 * @param {{ cwd?: string, stdin?: string, env?: Record<string, string>, title?: string, prompt?: string, onClose?: () => void }} [options]
 */
function startJob(id, command, args, { cwd, stdin, env, title = id, prompt, onClose } = {}) {
  const run = launch(command, args);
  const log = shared.logs.job(id, { title, command: [command, ...args], cwd, ...(prompt ? { prompt } : {}) });
  // stdin is a pipe only when there is something to send (checked below).
  const child = /** @type {import('node:child_process').ChildProcessWithoutNullStreams} */ (spawn(run.file, run.args, {
    cwd,
    shell: run.shell,
    windowsHide: true,
    env: childEnv(env),
    stdio: [stdin === undefined ? 'ignore' : 'pipe', 'pipe', 'pipe'],
  }));
  shared.jobs.set(id, { child, title });
  if (stdin !== undefined) child.stdin.end(stdin);
  const relay = (stream) => (chunk) => {
    const text = chunk.toString('utf8');
    log.write(text);
    shared.queue.output(id, stream, text);
    send('job:output', { id, stream, text });
  };
  child.stdout.on('data', relay('stdout'));
  child.stderr.on('data', relay('stderr'));
  child.on('error', (error) => {
    log.write(`${error.message}\n`);
    shared.queue.output(id, 'stderr', `${error.message}\n`);
    send('job:output', { id, stream: 'stderr', text: `${error.message}\n` });
  });
  child.on('close', (code) => {
    onClose?.();
    shared.jobs.delete(id);
    log.close(code);
    shared.queue.exited(id, code);
  });
}

function stopJob(id) {
  const job = shared.jobs.get(id);
  if (job) spawn('taskkill', ['/PID', String(job.child.pid), '/T', '/F'], { windowsHide: true });
}

// The CLI arguments of each kind of task. The workspace is fixed when the task is added.
function cliArgs(task) {
  const out = ['-o', task.workspace];
  switch (task.kind) {
    case 'download': {
      // A followed list's new videos: the collection knows the list and the folder.
      if (task.update) return ['collection', 'update', task.update, ...out, '--json'];
      const args = ['download', task.url, '-o', path.join(task.workspace, '下载'), '--json'];
      if (task.playlist) args.push('--playlist');
      if (task.collection) args.push('--collection', task.collection, '--workspace', task.workspace);
      if (task.follow) args.push('--follow');
      if (task.auto) args.push('--auto');
      return args;
    }
    case 'process': {
      // Processing asked for in the window always runs again; only an Agent reuses an earlier run.
      const args = ['process', task.video, ...out, '--json', '--force', '--frame-interval', String(task.interval)];
      if (task.maxFrames) args.push('--max-frames', String(task.maxFrames));
      if (task.bcut) args.push('--asr', 'bcut', '--allow-remote-asr'); // the user's BCut setting, on by default
      if (task.slides) args.push('--extract-slides');
      if (task.screenRegion) args.push('--screen-region', task.screenRegion);
      if (task.subtitles) args.push('--subtitles', task.subtitles);
      if (task.slidesFolder) args.push('--slides', task.slidesFolder);
      return args;
    }
    case 'frame':
      return ['frame', task.video, ...task.times, ...out];
    case 'compress':
      return ['compress', task.video, '--json'];
    case 'collection': {
      const args = ['summarize', '--collection', task.collection, ...out];
      if (task.model) args.push('--model', task.model);
      if (task.effort) args.push('--effort', task.effort);
      if (task.template) args.push('--template', task.template);
      if (task.guide) args.push('--guide');
      if (task.request) args.push('--request', task.request);
      if (task.overwrite) args.push('--overwrite');
      return args;
    }
    case 'summary': {
      const args = ['summarize', task.video, ...out];
      if (task.model) args.push('--model', task.model);
      if (task.effort) args.push('--effort', task.effort);
      if (task.template) args.push('--template', task.template);
      if (task.request) args.push('--request', task.request);
      if (task.overwrite) args.push('--overwrite');
      return args;
    }
    default:
      throw new Error(`unknown task kind: ${task.kind}`);
  }
}

// A compression stopped from here is killed before it can delete its half-written copy beside the video (named by
// files.temporary_beside); the next compression of that video would remove it too, but it may never come.
function removeLeftovers(video) {
  const { dir, name, ext } = path.parse(video);
  const escape = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const pattern = new RegExp(`^\\.${escape(name)}\\.[0-9a-f]{8}\\.part${escape(ext)}$`);
  try {
    for (const file of fs.readdirSync(dir).filter((item) => pattern.test(item))) fs.rmSync(path.join(dir, file), { force: true });
  } catch (error) {
    shared.logs.line('warn', `could not remove what a stopped compression left beside ${video}: ${error.message}`);
  }
}

function startTask(task) {
  if (task.kind === 'summary' && task.route === 'deepseek') return chatRounds.startDeepSeek(task);
  if (['summary', 'collection'].includes(task.kind) && task.route !== 'api') return startAgent(task);
  const [command, ...prefix] = cliCommand();
  const args = [...prefix, ...cliArgs(task)];
  const options = { cwd: task.workspace, title: task.title };
  // A second later: FFmpeg, killed with the tree, may hold the file a moment longer than the CLI.
  if (task.kind === 'compress') options.onClose = () => task.stopping && setTimeout(() => removeLeftovers(task.video), 1000);
  const site = task.kind === 'download' && accounts.siteOf(task.url);
  if (!site) return startJob(task.id, command, args, options);
  // The site's cookies go to yt-dlp as a cookies file that lives as long as the download.
  accounts
    .writeCookies(site, path.join(cookiesDir(), `${task.id}.txt`))
    .then((cookies) => {
      if (task.stopping) return shared.queue.exited(task.id, -1);
      startJob(task.id, command, [...args, ...(cookies ? ['--cookies', cookies] : [])], {
        ...options,
        onClose: () => cookies && fs.rmSync(cookies, { force: true }),
      });
    })
    .catch((error) => {
      shared.queue.output(task.id, 'stderr', `${error.message}\n`);
      shared.queue.exited(task.id, -1);
    });
}

// Agent route: Claude Code with the plugin, or Codex or another agent told to follow the skill file.
function startAgent(task) {
  const { agent, video, folder, request, workspace, title } = task;
  const skill = path.join(pluginRoot(), 'skills', 'video-agent', 'SKILL.md');
  const file = task.guide ? '学习提纲.md' : '合集总结.md';
  const other = agent === 'claude' || agent === 'codex' ? null : otherAgents().find((entry) => entry.key === agent);
  if (agent !== 'claude' && agent !== 'codex' && !other) {
    shared.queue.output(task.id, 'stderr', `设置里没有 ${agent} 这个 Agent。\n`);
    return shared.queue.exited(task.id, -1);
  }
  const name = agent === 'claude' ? 'Claude Code' : agent === 'codex' ? 'Codex' : other.name;
  // An Agent writes files itself; keep the current text as a version first, so nothing is lost even if it overwrites.
  const [command, ...prefix] = cliCommand();
  const target = task.kind === 'collection'
    ? ['--collection', task.collection, ...(task.guide ? ['--guide'] : [])]
    : [video];
  spawnSync(command, [...prefix, 'versions', ...target, '-o', workspace, '--keep', name], { windowsHide: true, env: childEnv() });
  const save = (what, draft, args) =>
    `写成 ${draft}，再运行 video-agent summarize ${args} -o "${workspace}" --import --source "${task.model ? `${name} ${task.model}` : name}" 保存为 ${what}（它会删掉草稿；已经有 ${what} 时另存为一个版本，由用户决定用哪个）。`;
  const text = (task.kind === 'collection'
    ? [
        `为合集「${task.collection}」写 ${file}，按 skill 里「A collection」的做法。`,
        `工作区是 ${workspace}，合集文件夹是 ${folder}。先运行 video-agent collection show "${task.collection}" -o "${workspace}" 看各集的状态；还没有总结的视频先按 skill 写总结，几乎没有内容的视频用 collection skip 跳过并写明原因。不要上传音频。`,
        save(file, path.join(folder, file.replace(/\.md$/, '.draft.md')), `--collection "${task.collection}"${task.guide ? ' --guide' : ''}`),
      ]
    : [
        `总结这个视频：${video}`,
        `工作区是 ${workspace}，这个视频已经处理过，处理结果在 ${folder}。不要上传音频。`,
        save('总结.md', path.join(folder, '总结.draft.md'), `"${video}"`),
      ]
  ).concat(
    task.template ? [`按 video-agent template "${task.template}" 打印的规则和模板写，不用别的模板。`] : [],
    request ? [`用户的要求：${request}`] : [],
  ).filter(Boolean).join('\n');
  if (agent === 'claude') {
    const prompt = `用 video-agent skill 完成下面的任务。\n${text}`;
    startJob(task.id, 'claude', [
      '-p',
      '--plugin-dir', pluginRoot(),
      '--add-dir', workspace,
      '--permission-mode', 'acceptEdits',
      '--allowedTools', 'Bash(video-agent *)', 'Read', 'Write', 'Edit', 'Skill',
      '--output-format', 'stream-json', '--verbose',
      ...(task.model ? ['--model', task.model] : []),
      ...models.effortArgs('claude', task.effort),
    ], { cwd: workspace, stdin: prompt, title, prompt });
  } else if (agent === 'codex') {
    const prompt = `先读 ${skill} 并照它做，<video-agent> 用 video-agent 命令。\n${text}`;
    startJob(task.id, 'codex', [
      'exec', '--skip-git-repo-check', '--cd', workspace, '--sandbox', 'workspace-write', '--json',
      ...(task.model ? ['-m', task.model] : []), ...models.effortArgs('codex', task.effort), '-',
    ], { cwd: workspace, stdin: prompt, title, prompt });
  } else {
    const prompt = `先读 ${skill} 并照它做，<video-agent> 用 video-agent 命令。\n${text}`;
    const temporary = [];
    const { args: modelArgs, file: patch, after } = agentModel(task, other);
    if (patch) temporary.push(patch);
    // Without a model, {model} goes, and the option before it too (as in `--model {model}`).
    let args = other.args.flatMap((arg, i, all) => {
      if (task.model) return [arg === '{model}' ? task.model : arg];
      return arg === '{model}' || (all[i + 1] === '{model}' && arg.startsWith('-')) ? [] : [arg];
    });
    const at = after && args.includes(after) ? args.indexOf(after) + 2 : args.length;
    args.splice(at, 0, ...modelArgs);
    if (!args.includes('{prompt}') || args.indexOf('{prompt}') === args.length - 1) {
      args.splice(args.includes('{prompt}') ? args.length - 1 : args.length, 0, ...models.effortArgs(other.key, task.effort));
    }
    const onClose = () => temporary.forEach((file) => fs.rmSync(file, { force: true }));
    if (!args.includes('{prompt}')) return startJob(task.id, other.file, args, { cwd: workspace, stdin: prompt, title, prompt, onClose });
    // A command line keeps one line through cmd.exe, so the task goes in a file and the line points to it.
    const taskFile = path.join(app.getPath('temp'), `video-agent-task-${task.id}.md`);
    fs.writeFileSync(taskFile, prompt);
    temporary.push(taskFile);
    args = args.map((arg) => (arg === '{prompt}' ? `读 ${taskFile} 并完成里面的任务。` : arg));
    startJob(task.id, other.file, args, { cwd: workspace, title, prompt, onClose });
  }
}

// The options that run another agent with the model chosen for this task (none: its own default). DeepSeek Harness
// takes a patch file for its agent-default-model entry, whose config is replaced whole, so the provider it has now
// is kept beside the new model.
function agentModel(task, other) {
  const how = AGENTS[other.key]?.model;
  if (!task.model || !how || how === '{model}') return { args: [] };
  if (how !== 'patch') return { args: [how, task.model] };
  const profile = other.args[other.args.indexOf('--profile') + 1] || 'headless';
  const run = launch(other.file, ['--profile', profile, '--dump-config']);
  const dump = spawnSync(run.file, run.args, { encoding: 'utf8', windowsHide: true, shell: run.shell, env: childEnv() });
  const provider = /dsh-agent-default-model'?\s+config:\s+provider:\s*(\S+)/.exec(dump.stdout || '')?.[1];
  if (!provider) {
    shared.queue.output(task.id, 'stderr', `没读到 DeepSeek Harness 现在用的模型服务，用它的默认模型。\n`);
    return { args: [] };
  }
  const file = path.join(app.getPath('temp'), `video-agent-dsh-${task.id}.yml`);
  fs.writeFileSync(file, `- id: agent-default-model\n  config:\n    provider: ${provider}\n    model: ${JSON.stringify(task.model)}\n`);
  return { args: ['--patch', file], file, after: '--profile' }; // a launcher option: before the task, after the profile
}

// After a download: its new files are compressed when 压缩下载的视频 is on, then processed ("process after download")
// with the window's frame settings and BCut setting, without slides. Files the download found already saved, as when
// a collection of downloaded videos starts following its list, are left alone.
function followUp(task) {
  const { frameInterval, maxFrames, bcut, compressDownloads } = loadSettings();
  // Downloads are compressed first when the setting is on; processing follows the compression.
  if (task.kind === 'download' && compressDownloads !== false) {
    return (task.fresh || task.paths).map((video) => ({
      kind: 'compress', title: `压缩：${path.basename(video)}`, video, workspace: task.workspace, then: task.then,
    }));
  }
  const videos = task.kind === 'compress' ? [task.video] : task.kind === 'download' ? task.fresh || task.paths : [];
  if (task.then !== 'process') return [];
  return videos.map((video) => ({
    kind: 'process',
    title: `处理：${path.basename(video)}`,
    video,
    workspace: task.workspace,
    interval: task.interval ?? frameInterval,
    maxFrames: task.maxFrames ?? maxFrames,
    bcut: task.bcut ?? bcut, // a local video's answer in the window, else the BCut setting
  }));
}

function createQueue() {
  shared.queue = new TaskQueue({
    start: startTask,
    stop: (task) => (task.route === 'deepseek' ? chatRounds.stop() : stopJob(task.id)),
    changed: () => {
      updateTray();
      send('tasks:changed', shared.queue.list());
    },
    limits: () => ({ ...DEFAULT_LIMITS, ...loadSettings().limits }),
    followUp,
  });
}

module.exports = { createQueue };
