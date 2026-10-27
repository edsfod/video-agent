// Window logic. Every action runs the Video Agent CLI (or an Agent CLI) through window.va; nothing here touches media.

const $ = (id) => document.getElementById(id);
const state = {
  settings: null,
  env: null,
  videos: [], // { path, info, busy, error }
  current: null,
  tab: 'process',
  route: 'claude',
  job: null, // { id, title, handlers }
  term: null,
};
let jobCounter = 0;

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

// ---------- jobs and log ----------

function logShow(title) {
  $('log').hidden = false;
  $('log-title').textContent = title;
  $('log-text').textContent = '';
  $('cancel-job').hidden = false;
}

function logAppend(text) {
  const pre = $('log-text');
  const atBottom = pre.scrollHeight - pre.scrollTop - pre.clientHeight < 30;
  pre.textContent += text;
  if (atBottom) pre.scrollTop = pre.scrollHeight;
}

// Runs one job at a time. `start(id)` starts it; handlers see stdout lines and the exit code.
function runJob(title, start, { onLine, onExit, showStdout = true } = {}) {
  if (state.job) {
    alert('还有任务在运行，请等它结束或先停止。');
    return false;
  }
  const id = `job-${++jobCounter}`;
  state.job = { id, title, buffer: '', onLine, onExit, showStdout };
  logShow(title);
  start(id, title);
  return true;
}

window.va.onJobOutput(({ id, stream, text }) => {
  const job = state.job;
  if (!job || job.id !== id) return;
  if (stream === 'stderr' || job.showStdout) logAppend(text);
  if (stream !== 'stdout' || !job.onLine) return;
  job.buffer += text;
  const lines = job.buffer.split(/\r?\n/);
  job.buffer = lines.pop();
  for (const line of lines) if (line.trim()) job.onLine(line);
});

window.va.onJobExit(({ id, code }) => {
  const job = state.job;
  if (!job || job.id !== id) return;
  if (job.buffer.trim() && job.onLine) job.onLine(job.buffer);
  state.job = null;
  $('cancel-job').hidden = true;
  logAppend(`\n${code === 0 ? '完成' : `结束（退出码 ${code}）`}\n`);
  $('log-title').textContent = `${job.title} · ${code === 0 ? '完成' : '未完成'}`;
  job.onExit?.(code);
});

$('cancel-job').onclick = () => state.job && window.va.cancel(state.job.id);
$('close-log').onclick = () => ($('log').hidden = true);

// ---------- video list ----------

async function addVideos(paths) {
  for (const path of paths) {
    if (!state.videos.some((video) => video.path.toLowerCase() === path.toLowerCase())) {
      state.videos.push({ path, info: null });
    }
  }
  await persistList();
  renderList();
  if (paths.length) await select(paths[paths.length - 1]);
  await Promise.all(state.videos.filter((video) => !video.info).map(refresh));
}

async function persistList() {
  state.settings = await window.va.saveSettings({ videos: state.videos.map((video) => video.path) });
}

function badge(video) {
  if (video.busy) return element('span', { className: 'badge busy', textContent: video.busy });
  if (video.error) return element('span', { className: 'badge error', textContent: '无法读取' });
  if (!video.info) return element('span', { className: 'badge', textContent: '…' });
  if (video.info.summary) return element('span', { className: 'badge done', textContent: '已总结' });
  if (video.info.processed) return element('span', { className: 'badge', textContent: '已处理' });
  return element('span', { className: 'badge', textContent: '未处理' });
}

function renderList() {
  const list = $('video-list');
  list.replaceChildren(
    ...state.videos.map((video) => {
      const item = element('div', { className: 'video-item' + (video.path === state.current ? ' active' : '') }, [
        element('span', { className: 'name', textContent: baseName(video.path), title: video.path }),
        badge(video),
      ]);
      item.onclick = () => select(video.path);
      return item;
    }),
  );
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
}

async function select(path) {
  state.current = path;
  renderList();
  renderVideo();
}

// ---------- video view ----------

function renderVideo() {
  const video = current();
  $('empty').hidden = !!video;
  $('video').hidden = !video;
  if (!video) return;
  $('video-name').textContent = baseName(video.path);
  $('video-path').textContent = video.path;
  $('reveal-folder').disabled = !video.info?.processed;
  renderTab();
}

function renderTab() {
  for (const button of document.querySelectorAll('.tabs button')) {
    button.classList.toggle('active', button.dataset.tab === state.tab);
  }
  for (const panel of document.querySelectorAll('.panel')) {
    panel.hidden = panel.dataset.panel !== state.tab;
    if (!panel.hidden) panel.scrollTop = 0;
  }
  const video = current();
  if (!video) return;
  ({ process: renderProcess, transcript: renderTranscript, frames: renderFrames, summary: renderSummary, terminal: renderTerminal })[
    state.tab
  ](video);
}

for (const button of document.querySelectorAll('.tabs button')) {
  button.onclick = () => {
    state.tab = button.dataset.tab;
    renderTab();
  };
}

function renderProcess(video) {
  $('opt-interval').value = state.settings.frameInterval;
  $('opt-max-frames').value = state.settings.maxFrames;
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
      const source = sources[transcript.source] || transcript.source.replace(/^sidecar:/, '字幕文件：').replace(/^embedded:/, '内嵌字幕：');
      facts.push(['字幕', `${transcript.segments} 段 · ${source}`]);
      if (transcript.error) facts.push(['字幕问题', transcript.error]);
      facts.push(['代表画面', `${manifest.representative_frames.length} 张，补截 ${info.extra_frames.length} 张`]);
      if (manifest.slide_extraction.enabled) facts.push(['PPT', `${manifest.slide_extraction.slides.length} 张`]);
      facts.push(['总结', info.summary ? '已生成' : '还没有']);
      facts.push(['处理结果', info.folder, 'wide']);
    }
    $('process-state').textContent = info.processed ? '已处理过；再次处理会重新抽取画面，已有字幕保留。' : '';
    $('run-process').textContent = info.processed ? '重新处理' : '开始处理';
  }
  $('facts').replaceChildren(
    ...facts.map(([label, value, size]) =>
      element('div', { className: 'fact' + (size ? ' ' + size : '') }, [
        element('div', { className: 'label', textContent: label }),
        element('div', { className: 'value', textContent: value }),
      ]),
    ),
  );
}

$('run-process').onclick = async () => {
  const video = current();
  const interval = Number($('opt-interval').value) || 60;
  const maxFrames = Number($('opt-max-frames').value) || 36;
  state.settings = await window.va.saveSettings({ frameInterval: interval, maxFrames });
  const args = ['process', video.path, '-o', state.settings.workspace, '--json'];
  args.push('--frame-interval', String(interval), '--max-frames', String(maxFrames));
  if ($('opt-bcut').checked) args.push('--asr', 'bcut', '--allow-remote-asr');
  if ($('opt-slides').checked) args.push('--extract-slides');
  const started = runJob(`处理：${baseName(video.path)}`, (id, title) => window.va.startCli(id, args, undefined, title), {
    showStdout: false,
    onLine(line) {
      try {
        const result = JSON.parse(line);
        if (result.error) logAppend(`错误：${result.error}\n`);
        else if (result.transcript_error) logAppend(`字幕没有拿到：${result.transcript_error}\n`);
      } catch {
        logAppend(line + '\n');
      }
    },
    async onExit() {
      video.busy = null;
      $('opt-bcut').checked = false; // consent covers one run only
      await refresh(video);
    },
  });
  if (started) {
    video.busy = '处理中';
    renderList();
  }
};

async function renderTranscript(video) {
  const box = $('transcript');
  if (!video.info?.transcript) {
    box.replaceChildren(element('p', { className: 'muted', textContent: '还没有字幕。先在「处理」里处理这个视频。' }));
    $('transcript-count').textContent = '';
    return;
  }
  const text = await window.va.read(video.info.transcript);
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

function renderFrames(video) {
  const box = $('frames');
  const manifest = video.info?.manifest;
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
  box.replaceChildren(
    ...items.map((item) => {
      const card = element('div', { className: 'frame' + (item.extra ? ' extra' : '') }, [
        element('img', { src: fileUrl(item.file), alt: '' }),
        element('div', { textContent: clock(item.time) }),
      ]);
      card.onclick = () => showImage(item.file, clock(item.time));
      return card;
    }),
  );
}

$('frame-form').onsubmit = (event) => {
  event.preventDefault();
  const video = current();
  const times = $('frame-times').value.trim().split(/[\s,，]+/).filter(Boolean);
  if (!times.length || !video.info?.processed) return;
  runJob(`补截画面：${times.join(' ')}`, (id, title) =>
    window.va.startCli(id, ['frame', video.path, ...times, '-o', state.settings.workspace], undefined, title),
  { onExit: () => refresh(video) });
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
  copy: '把规则、模板和字幕材料复制到剪贴板，贴进任何聊天 AI。画面不会一起复制，可以在「画面」里另外附上。',
};

function renderRoutes() {
  for (const input of document.querySelectorAll('input[name=route]')) {
    const missing = (input.value === 'claude' && !state.env.claude) || (input.value === 'codex' && !state.env.codex);
    input.disabled = missing;
    input.parentElement.classList.toggle('unavailable', missing);
    input.parentElement.title = missing ? `没有找到 ${input.value} 命令` : '';
    input.checked = input.value === state.route;
    input.onchange = () => {
      state.route = input.value;
      renderSummary(current());
    };
  }
  $('route-note').textContent = ROUTE_NOTES[state.route];
}

async function renderSummary(video) {
  renderRoutes();
  const article = $('summary');
  const info = video.info;
  $('run-summary').disabled = !info?.processed;
  $('run-summary').textContent = state.route === 'copy' ? '复制材料' : info?.summary ? '重新生成总结' : '生成总结';
  $('open-summary').hidden = !info?.summary;
  if (!info?.processed) {
    article.replaceChildren(element('p', { className: 'placeholder', textContent: '先在「处理」里处理这个视频，再生成总结。' }));
    return;
  }
  if (!info.summary) {
    article.replaceChildren(element('p', { className: 'placeholder', textContent: '还没有总结。' }));
    return;
  }
  const text = await window.va.read(info.summary);
  article.innerHTML = DOMPurify.sanitize(marked.parse(text || ''));
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

$('open-summary').onclick = () => current()?.info?.summary && window.va.open(current().info.summary);

$('run-summary').onclick = async () => {
  const video = current();
  const info = video.info;
  const request = $('summary-request').value.trim();
  if (state.route === 'copy') return copyMaterial(info);
  if (info.summary && !confirm('已经有总结了，要重新生成并覆盖吗？')) return;
  const done = async () => {
    video.busy = null;
    await refresh(video);
  };
  let started;
  if (state.route === 'api') {
    const args = ['summarize', video.path, '-o', state.settings.workspace];
    if (request) args.push('--request', request);
    if (info.summary) args.push('--overwrite');
    started = runJob(`总结（模型 API）：${baseName(video.path)}`, (id, title) => window.va.startCli(id, args, undefined, title), {
      onExit: done,
    });
  } else {
    const agent = state.route;
    started = runJob(
      `总结（${agent === 'claude' ? 'Claude Code' : 'Codex'}）：${baseName(video.path)}`,
      (id, title) =>
        window.va.startAgent({ id, title, agent, video: video.path, folder: info.folder, request, overwrite: !!info.summary }),
      { showStdout: false, onLine: agent === 'claude' ? claudeLine : codexLine, onExit: done },
    );
  }
  if (started) {
    video.busy = '总结中';
    renderList();
  }
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

async function copyMaterial(info) {
  const template = await window.va.cliText(['template']);
  const context = await window.va.read(info.context);
  const request = $('summary-request').value.trim();
  const text = [
    '请按下面的规则和模板，为这个视频写一篇总结（Markdown）。',
    request ? `我的要求：${request}` : '',
    template.out,
    '---',
    context,
  ].filter(Boolean).join('\n\n');
  await window.va.copy(text);
  $('summary-state').textContent = `已复制 ${text.length} 个字符。画面在处理结果的 frames 文件夹里。`;
  setTimeout(() => ($('summary-state').textContent = ''), 8000);
}

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
  const id = `pty-${++jobCounter}`;
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

$('add-videos').onclick = async () => addVideos(await window.va.pickVideos());

$('download-form').onsubmit = (event) => {
  event.preventDefault();
  const url = $('download-url').value.trim();
  if (!url) return;
  const folder = joinPath(state.settings.workspace, '下载');
  const saved = [];
  runJob(`下载：${url}`, (id, title) => window.va.startCli(id, ['download', url, '-o', folder, '--json'], undefined, title), {
    showStdout: false,
    onLine(line) {
      try {
        saved.push(JSON.parse(line).path);
      } catch {
        logAppend(line + '\n');
      }
    },
    async onExit() {
      if (saved.length) {
        $('download-url').value = '';
        await addVideos(saved);
      }
    },
  });
};

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
  if (paths.length) addVideos(paths);
});

// ---------- settings ----------

$('open-settings').onclick = async () => {
  $('set-workspace').value = state.settings.workspace;
  $('set-cli').value = state.settings.cli;
  $('set-key').value = '';
  $('set-close-to-tray').checked = state.settings.closeToTray !== false;
  const cli = state.env.bundled ? '安装程序自带的 video-agent' : state.env.cli.join(' ');
  $('env-info').textContent =
    `正在用的命令：${cli} · Claude Code：${state.env.claude ? '已找到' : '没有找到'} · Codex：${state.env.codex ? '已找到' : '没有找到'}`;
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
  $('settings').showModal();
};

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
    closeToTray: $('set-close-to-tray').checked,
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
  if (workspaceChanged) await Promise.all(state.videos.map(refresh));
});

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
window.va.onTrayAddVideos(async () => addVideos(await window.va.pickVideos()));

// ---------- start ----------

async function init() {
  state.settings = await window.va.settings();
  state.env = await window.va.env();
  state.route = state.env.claude ? 'claude' : state.env.codex ? 'codex' : 'api';
  state.videos = state.settings.videos.map((path) => ({ path, info: null }));
  renderList();
  if (state.videos.length) select(state.videos[0].path);
  else renderVideo();
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
