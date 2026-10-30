// End-to-end test: drives the real window with Playwright and the real Video Agent CLI on a synthetic video.
// The model is a local fake; CLI settings live in a temporary %APPDATA%. Run with `npm test`.

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { _electron: electron } = require('playwright-core');

const GUI = path.resolve(__dirname, '..');
const ROOT = fs.mkdtempSync(path.join(os.tmpdir(), 'va-e2e-'));
const WORKSPACE = path.join(ROOT, 'workspace');
const APPDATA = path.join(ROOT, 'appdata');
const VIDEO = path.join(ROOT, 'media', 'sample clip [e2e].mp4');
// From a checkout, the repository's own CLI (.venv) comes first on PATH: an installed Video Agent's copy, which the
// installer puts on PATH for agents and the terminal, would otherwise answer for an older version.
const VENV = path.resolve(GUI, '..', '.venv', 'Scripts');
const PATH_KEY = Object.keys(process.env).find((key) => key.toUpperCase() === 'PATH') || 'PATH';
const SEARCH = fs.existsSync(VENV) && !process.env.VA_E2E_EXE ? `${VENV};${process.env[PATH_KEY]}` : process.env[PATH_KEY];
// DeepSeek's web chat is a local page with the parts deepseek.js uses (written in test.before).
const DEEPSEEK_PAGE = path.join(ROOT, 'deepseek.html');
const ENV = {
  ...process.env,
  [PATH_KEY]: SEARCH,
  VA_E2E_BACKGROUND: '1',
  VA_DEEPSEEK_URL: require('node:url').pathToFileURL(DEEPSEEK_PAGE).href,
  // AutoSlides Extractor, which finds the screen pages where it is installed, is left out: results must not depend
  // on the machine.
  AUTOSLIDES_EXTRACTOR: 'none',
  VA_DEEPSEEK_RETRY_MS: '500',
  VA_DEEPSEEK_START_MS: '6000',
  APPDATA,
  NO_PROXY: '127.0.0.1,localhost',
  no_proxy: '127.0.0.1,localhost',
};
const SUMMARY = '# 测试视频\n\n## 概要\n\n一段测试视频。[画面](frames/extra/frame-00-00-03.jpg)\n';

function cli(args) {
  return execFileSync('video-agent', args, { env: ENV, encoding: 'utf8', windowsHide: true });
}

function makeVideo() {
  fs.mkdirSync(path.dirname(VIDEO), { recursive: true });
  // Filter sources and mpeg4, so that the LGPL FFmpeg the installer ships can make it too (no lavfi, no libx264).
  execFileSync('ffmpeg', [
    '-y', '-hide_banner', '-loglevel', 'error',
    '-filter_complex', 'testsrc=duration=4:size=320x240:rate=10[a];smptebars=duration=4:size=320x240:rate=10[b];'
      + '[a][b]concat=n=2:v=1:a=0[v];sine=frequency=440:duration=8[s]',
    '-map', '[v]', '-map', '[s]', '-c:v', 'mpeg4', '-q:v', '3', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', VIDEO,
  ]);
  fs.writeFileSync(VIDEO.replace(/\.mp4$/, '.srt'),
    '1\n00:00:00,500 --> 00:00:02,500\n大家好，今天讲测试视频\n\n2\n00:00:03,000 --> 00:00:05,000\n我们看看这张图表\n');
}

// A fake OpenAI-compatible server: the first reply asks for a frame, the second returns the summary.
function fakeModel() {
  const requests = [];
  const replies = [
    { choices: [{ message: { role: 'assistant', content: null, tool_calls: [
      { id: 'c1', type: 'function', function: { name: 'frame', arguments: '{"time":"00:00:03"}' } }] } }] },
    { choices: [{ message: { role: 'assistant', content: SUMMARY } }] },
  ];
  const server = http.createServer((request, response) => {
    // The model list (video-agent models), which costs no tokens.
    if (request.method === 'GET') return response.end(JSON.stringify({ data: [{ id: 'fake-model' }, { id: 'chosen-model' }] }));
    let body = '';
    request.on('data', (chunk) => (body += chunk));
    request.on('end', () => {
      requests.push(JSON.parse(body));
      response.setHeader('Content-Type', 'application/json');
      response.end(JSON.stringify(replies.shift()));
    });
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve({ server, requests })));
}

// The packaged build (VA_E2E_EXE, in CI's installer job) runs only the tests that reach what packaging changes: the
// bundled CLI and FFmpeg, the plugin and skill files under resources, the licence and privacy files, the terminal's
// native module, the tray icon and cookie encryption. The rest, declared with devTest, run on the unpackaged app alone (user request, 2026-10-29: the
// whole suite ran twice).
const devTest = (name, fn) => test(name, { skip: !!process.env.VA_E2E_EXE && 'runs on the unpackaged app' }, fn);

let app;
let page;

// Waits until the saved settings pass `check`. page.waitForFunction would not wait for an async predicate: the promise
// it returns already counts as true.
async function saved(check, timeout = 15_000) {
  for (const end = Date.now() + timeout; ; await new Promise((resolve) => setTimeout(resolve, 100))) {
    const settings = await page.evaluate(() => window.va.settings());
    if (check(settings)) return settings;
    if (Date.now() > end) assert.fail(`the settings were not saved as expected: ${JSON.stringify(settings).slice(0, 500)}`);
  }
}
// The parts of chat.deepseek.com that deepseek.js drives. The second file of the first message fails to upload once;
// the first message hangs at 正在分析图片 and the second gets a busy notice, as DeepSeek's servers give at times; then
// the answer asks for pictures in a 画面调整 section, and the next round's (its prompt starts with the candidates taken),
// its 复查 finding nothing more and the sections it leaves out said, ends the rounds. Each answer takes the place of the
// oldest one on the page, as the real page drops earlier answers. What it was sent and every file attached are kept in
// localStorage, which outlives loading the page again.
const FAKE_DEEPSEEK = `<!doctype html><meta charset="utf-8"><title>DeepSeek</title>
<div id="chat"></div>
<div><div><div><div><div><div>
  <div id="attachments"></div>
  <textarea></textarea>
  <div class="ds-toggle-button">DeepThink</div><div class="ds-toggle-button ds-toggle-button--selected">Search</div>
  <input type="file" multiple hidden>
  <div id="send" role="button" class="ds-button ds-button--primary ds-button--circle ds-button--disabled"><svg><path d="M8 1"/></svg></div>
</div></div></div></div></div></div>
<script>
  const box = document.querySelector('textarea');
  const send = document.getElementById('send');
  const icon = send.querySelector('path');
  const attachments = document.getElementById('attachments');
  window.sent = JSON.parse(localStorage.getItem('sent') || '[]');
  window.attached = JSON.parse(localStorage.getItem('attached') || '[]');
  document.querySelector('input').onchange = (event) => {
    for (const file of event.target.files) {
      const item = document.createElement('div');
      item.className = 'ds-animated-size-item';
      item.innerHTML = '<div role="button" tabindex="0"><img><div tabindex="0">×</div></div>';
      item.querySelector('img').alt = file.name;
      item.querySelector('[tabindex="0"] [tabindex="0"]').onclick = () => item.remove();
      attachments.append(item);
      window.attached.push(file.name);
      const fails = window.attached.length === 2;
      item.dataset.uploading = '';
      setTimeout(() => (delete item.dataset.uploading, fails && item.append('Upload failed')), 300);
    }
    localStorage.setItem('attached', JSON.stringify(window.attached));
  };
  for (const button of document.querySelectorAll('.ds-toggle-button')) button.onclick = () => button.classList.toggle('ds-toggle-button--selected');
  setInterval(() => send.classList.toggle('ds-button--disabled', !box.value || !!attachments.querySelector('[data-uploading]')), 50);
  send.onclick = () => {
    if (!box.value) return;
    const text = box.value;
    const files = [...attachments.querySelectorAll('img')].map((img) => img.alt);
    const toggles = [...document.querySelectorAll('.ds-toggle-button--selected')].map((button) => button.textContent);
    window.sent.push({ text, files, toggles });
    localStorage.setItem('sent', JSON.stringify(window.sent));
    const hangs = window.sent.length === 1;
    const busy = window.sent.length === 2;
    box.value = '';
    attachments.replaceChildren();
    icon.setAttribute('d', 'M2 4'); // the stop square while writing
    if (hangs) return document.getElementById('chat').append('正在分析图片');
    setTimeout(() => {
      const next = text.startsWith('我照你上一稿');
      const answer = document.createElement('div');
      answer.className = 'ds-markdown';
      const code = document.createElement('pre');
      if (busy) answer.textContent = '服务器繁忙，请稍后再试。';
      else code.textContent = '# 测试视频\\n\\n视频：x · 时长：0:08\\n\\n## 概要\\n\\n' +
        (next ? '第二轮写的测试总结，用上了补截的候选。\\n\\n## 画面调整\\n\\n无\\n\\n## 复查\\n\\n- 删掉的节：要点、时间线、详细内容、需留意、需确认（测试视频只有 8 秒）\\n' : '第一轮写的测试总结，讲了彩条和测试图案。\\n\\n## 画面调整\\n\\n- 补截：00:00:01–00:00:06 彩条\\n');
      if (!busy) answer.append(code);
      document.querySelector('.ds-markdown')?.remove();
      document.getElementById('chat').append(answer);
      icon.setAttribute('d', 'M8 1');
    }, 2500);
  };
</script>`;

// Every confirm() is accepted unless a test asks for the other answer (refuse). They are answered inside the page:
// Electron shows confirm() and alert() as native message boxes, which Windows brings onto the screen even for a window
// placed off it (user report, 2026-10-29: two showed on the desktop during a test run).
const answerDialogs = () =>
  page.evaluate(() => {
    window.vaRefuse = false;
    window.confirm = () => !window.vaRefuse;
    window.alert = () => {};
  });
const refuse = (value) => page.evaluate((answer) => (window.vaRefuse = answer), value);
let model;

test.before(async () => {
  makeVideo();
  fs.writeFileSync(DEEPSEEK_PAGE, FAKE_DEEPSEEK);
  model = await fakeModel();
  cli(['config', '--provider', 'openai', '--model', 'fake-model', '--base-url', `http://127.0.0.1:${model.server.address().port}/v1`]);
  const userData = path.join(ROOT, 'gui-data');
  fs.mkdirSync(userData, { recursive: true });
  fs.writeFileSync(path.join(userData, 'settings.json'), JSON.stringify({ workspace: WORKSPACE, videos: [VIDEO], shell: 'cmd', checkUpdates: false }));
  // VA_E2E_EXE=<path to Video Agent.exe> runs the same tests against a packaged build.
  const packaged = process.env.VA_E2E_EXE;
  app = await electron.launch({
    executablePath: packaged || require('electron'),
    args: [...(packaged ? [] : ['.']), `--user-data=${userData}`],
    cwd: GUI,
    env: ENV,
  });
  page = await app.firstWindow();
  page.on('dialog', (dialog) => dialog.accept()); // only if one gets past answerDialogs
  await answerDialogs();
  await page.waitForSelector('#video-list .video-item .badge:text("未处理")');
  // Nothing is open at start; the tests work on the one video.
  assert.equal(await page.isVisible('#empty-pick'), true);
  await page.click('#video-list .video-item');
  await page.waitForSelector('#video:not([hidden])');
});

// A test that fails halfway can leave a dialog open or a stub in place, which would fail every test after it.
test.afterEach(async () => {
  await refuse(false).catch(() => {});
  await app?.evaluate(() => {
    globalThis.vaRestoreDialogs?.();
    delete globalThis.vaRestoreDialogs;
  }).catch(() => {});
  await page?.evaluate(() => document.querySelectorAll('dialog[open]').forEach((dialog) => dialog.close())).catch(() => {});
});

test.after(async () => {
  await app?.close();
  model?.server.close();
  fs.rmSync(ROOT, { recursive: true, force: true });
});

test('process the video from the window', async () => {
  await page.click('#run-process');
  await page.waitForSelector('#video-list .video-item .badge:text("已处理")', { timeout: 60_000 });
  const facts = await page.textContent('#facts');
  assert.match(facts, /2 段 · 同名字幕文件/); // the file name, long for downloads, only as the card's tooltip
  assert.equal(await page.getAttribute('#facts .fact:nth-child(2)', 'title'), 'sample clip [e2e].srt');
  assert.match(facts, /布局整个画面是屏幕/);
  await page.waitForSelector('#layout-card:not([hidden]) #layout-image');
  assert.match(await page.textContent('#log-text'), /完成/);
});

devTest('the same processing is queued once, and the queue empties when it ends', async () => {
  await Promise.all([page.click('#run-process'), page.click('#run-process')]);
  await page.waitForFunction(() => document.querySelector('#task-note').textContent.includes('已经在队列里'));
  assert.equal(await page.locator('.task-item', { hasText: '处理：' }).count(), 2); // the first run and this one
  await page.waitForFunction(() => document.querySelector('#open-tasks').textContent === '任务', null, { timeout: 60_000 });
  await page.waitForSelector('#video-list .video-item .badge:text("已处理")');
});

devTest('transcript tab lists the lines', async () => {
  await page.click('.tabs button[data-tab=transcript]');
  await page.waitForSelector('#transcript .line');
  assert.equal(await page.locator('#transcript .line').count(), 2);
  await page.fill('#transcript-filter', '图表');
  await page.waitForFunction(() => document.querySelectorAll('#transcript .line').length === 1);
});

devTest('a correction gives a cleaned transcript and keeps the original', async () => {
  await page.fill('#transcript-filter', '');
  await page.click('#corrections summary');
  await page.fill('#correction-wrong', '测试视频');
  await page.fill('#correction-right', '示例视频');
  await page.click('#corrections-form button[type=submit]');
  await page.waitForFunction(() => document.querySelector('#transcript').textContent.includes('今天讲示例视频'));
  assert.match(await page.textContent('#corrections-state'), /改动了 1 行/);
  await page.check('#transcript-original');
  await page.waitForFunction(() => document.querySelector('#transcript').textContent.includes('今天讲测试视频'));
  await page.uncheck('#transcript-original');
  await page.click('#corrections-list button');
  await page.waitForFunction(() => document.querySelector('#corrections-list').children.length === 0);
  await page.waitForFunction(() => document.querySelector('#transcript').textContent.includes('今天讲测试视频'));
});

devTest('frames tab takes an extra frame', async () => {
  await page.click('.tabs button[data-tab=frames]');
  await page.waitForSelector('.frame img');
  await page.fill('#frame-times', '0:05');
  await page.click('#frame-form button[type=submit]');
  await page.waitForSelector('.frame.extra', { timeout: 30_000 });
  const loaded = await page.$eval('.frame.extra img', (img) => img.complete && img.naturalWidth > 0);
  assert.ok(loaded, 'the extra frame image loads from file://');
});

test('summary through the model API, with one frame tool round', async () => {
  await page.click('.tabs button[data-tab=summary]');
  assert.equal(await page.getAttribute('#routes label:first-child input', 'value'), 'copy', '复制材料 comes first');
  assert.equal(await page.locator('input[name=route]:checked').count(), 0, 'no route is chosen for the user');
  assert.equal(await page.isDisabled('#run-summary'), true);
  await page.check('input[name=route][value=api]');
  // A model chosen on the page for this route, instead of the one in the settings.
  // A model from the provider's list and a thinking level, instead of the model in the settings.
  await page.waitForSelector('#route-model option[value="chosen-model"]', { state: 'attached' });
  await page.selectOption('#route-model', 'chosen-model');
  await saved((settings) => settings.routeModels?.api === 'chosen-model');
  await page.selectOption('#route-effort', 'high');
  await saved((settings) => settings.routeEfforts?.api === 'high');
  await page.click('#run-summary');
  await page.waitForSelector('#summary h1:text("测试视频")', { timeout: 60_000 });
  assert.equal(model.requests[0].model, 'chosen-model');
  assert.equal(model.requests[0].reasoning_effort, 'high');
  assert.equal(await page.isHidden('#route-model-label'), false);
  // A model not in the list is typed in.
  await page.selectOption('#route-model', { label: '自定义…' });
  await page.fill('#route-model-custom', 'typed-model');
  await page.press('#route-model-custom', 'Tab');
  await saved((settings) => settings.routeModels?.api === 'typed-model');
  await page.selectOption('#route-model', '');
  await page.selectOption('#route-effort', '');
  await saved((settings) => !settings.routeModels?.api && !settings.routeEfforts?.api);
  assert.equal(model.requests.length, 2);
  assert.equal(model.requests[0].tools[0].function.name, 'frame');
  assert.equal(model.requests[1].messages.at(-1).content[1].type, 'image_url');
  await page.waitForSelector('#video-list .video-item .badge:text("已总结")');
  await page.click('#summary a');
  await page.waitForSelector('#lightbox[open]');
  await page.click('#lightbox');
});

devTest('summary through DeepSeek\'s web chat, in rounds until it asks for no more pictures', async () => {
  await page.click('.tabs button[data-tab=summary]');
  await page.check('input[name=route][value=deepseek]');
  await page.click('#run-summary');
  const done = async () => {
    for (const end = Date.now() + 120_000; ; await new Promise((resolve) => setTimeout(resolve, 500))) {
      const task = (await page.evaluate(() => window.va.tasks())).find((item) => item.title.startsWith('总结（DeepSeek 网页'));
      if (task && !['queued', 'running'].includes(task.status)) return task;
      if (Date.now() > end) assert.fail('the DeepSeek task did not end');
    }
  };
  const task = await done();
  const output = await page.evaluate((id) => window.va.taskOutput(id), task.id);
  assert.equal(task.status, 'done', JSON.stringify(output).slice(-1500));
  const sent = await app.evaluate(({ BrowserWindow }) =>
    BrowserWindow.getAllWindows().find((win) => win.getTitle() === 'DeepSeek').webContents.executeJavaScript('window.sent'));
  assert.equal(sent.length, 4, 'sent again after it hung and after the busy notice; a second round for the pictures, then none');
  assert.equal(sent[1].text, sent[0].text, 'the same message again');
  assert.equal(sent[2].text, sent[0].text, 'the same message again');
  assert.match(sent[2].text, /# Writing a video summary/);
  assert.deepEqual(sent[2].toggles, ['DeepThink', 'Search'], 'DeepThink and Search on');
  assert.ok(sent[2].files.length > 0 && sent[2].files.every((name) => name.endsWith('.jpg')));
  const attached = await app.evaluate(({ BrowserWindow }) =>
    BrowserWindow.getAllWindows().find((win) => win.getTitle() === 'DeepSeek').webContents.executeJavaScript('window.attached'));
  assert.deepEqual([...sent[0].files].sort(), [...sent[2].files].sort(), 'the file that failed to upload went with the rest');
  assert.equal(attached.slice(0, sent[0].files.length + 1).filter((name) => name === attached[1]).length, 2, 'only that file attached again');
  assert.ok(output.some(([, text]) => text.includes('单独重新上传')), 'the upload retry is in the task output');
  assert.match(sent[3].text, /^我照你上一稿/, 'the second answer found, though the page kept no more answers than before');
  assert.ok(sent[3].files.length >= 1 && sent[3].files.every((name) => name.includes('补截')));
  assert.ok(output.some(([, text]) => text.includes('正在分析图片')), 'the hang is in the task output');
  assert.ok(output.some(([, text]) => text.includes('服务器繁忙')), 'the retry is in the task output');
  // A summary was there already (the model API's), so both rounds are kept as versions beside it.
  const versions = JSON.parse(cli(['versions', VIDEO, '-o', WORKSPACE, '--json'])).versions.filter((item) => item.source === 'DeepSeek 网页');
  assert.deepEqual(versions.map((item) => item.note).sort(), ['第 1 轮', '第 2 轮']);
});

devTest('copy material puts the rules and transcript on the clipboard', async () => {
  await page.check('input[name=route][value=copy]');
  await page.click('#run-summary');
  await page.waitForFunction(() => document.querySelector('#summary-state').textContent.includes('已复制'));
  const copied = await app.evaluate(({ clipboard }) => clipboard.readText());
  assert.match(copied, /# Writing a video summary/);
  assert.match(copied, /我们看看这张图表/);
});

// Stands in for pi, Hermes Agent and the like: the task comes on standard input, or in the file its command line
// names where the command has {prompt}; it saves a summary the way the task says.
const FAKE_AGENT = `
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const file = /读 (.+) 并完成里面的任务/.exec(process.argv.slice(2).join(' '))?.[1];
const task = file ? fs.readFileSync(file, 'utf8') : fs.readFileSync(0, 'utf8');
const video = /总结这个视频：(.+)/.exec(task)[1].trim();
const workspace = /工作区是 (.+?)，/.exec(task)[1];
const draft = /写成 (.+?\\.draft\\.md)，/.exec(task)[1];
fs.writeFileSync(draft, '# 别的 Agent 写的\\n\\n## 概要\\n\\n这是另一个 Agent 按 skill 写的测试总结，任务来自' + (file ? '文件' : '标准输入') + '。\\n');
execFileSync('video-agent', ['summarize', video, '-o', workspace, '--import', '--source', /--source "([^"]+)"/.exec(task)[1]]);
if (fs.existsSync(draft)) throw new Error('the import left the draft');
`;

devTest('another agent writes a summary from standard input or from a task file', async () => {
  const script = path.join(ROOT, 'fake-agent.js');
  fs.writeFileSync(script, FAKE_AGENT);
  const versions = () => JSON.parse(cli(['versions', VIDEO, '-o', WORKSPACE, '--json'])).versions;
  for (const [command, from] of [[`"${process.execPath}" "${script}"`, '标准输入'], [`"${process.execPath}" "${script}" {prompt}`, '文件']]) {
    await page.click('#open-settings');
    await page.waitForSelector('#settings[open]');
    await page.check('#set-agents input[data-agent=custom]');
    await page.fill('#set-agents input[data-agent-command=custom]', command);
    await page.click('#save-settings');
    await page.click('.tabs button[data-tab=summary]');
    await page.waitForSelector('#routes .route-agent:has-text("node")');
    await page.check('input[name=route][value=custom]');
    await page.click('#run-summary');
    let found;
    for (let i = 0; i < 120 && !found; i++) {
      await new Promise((resolve) => setTimeout(resolve, 250));
      found = versions().find((version) => fs.readFileSync(version.path, 'utf8').includes(`任务来自${from}`));
    }
    if (!found) {
      const logs = path.join(ROOT, 'gui-data', 'logs', 'jobs');
      const [last] = fs.readdirSync(logs).map((name) => path.join(logs, name)).sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs);
      assert.fail(`no version written from the task on ${from}; the job's log:\n${last && fs.readFileSync(last, 'utf8').slice(-1500)}`);
    }
    assert.equal(found.source, 'node');
  }
  await page.click('#open-settings');
  for (const key of ['custom', 'pi', 'hermes', 'dsh']) await page.uncheck(`#set-agents input[data-agent=${key}]`);
  await page.click('#save-settings');
  await page.waitForSelector('#routes .route-agent:has-text("其他 Agent")');
  // With none chosen it still shows, says where to choose one, and writes nothing.
  await page.check('input[name=route][value=other]');
  assert.match(await page.textContent('#route-note'), /设置.*其他 Agent/);
  assert.equal(await page.isDisabled('#run-summary'), true);
  await page.check('input[name=route][value=api]');
});

devTest('a version note is edited in a dialog that starts from the note it has', async () => {
  const listed = () => JSON.parse(cli(['versions', VIDEO, '-o', WORKSPACE, '--json']));
  const [version] = listed().versions;
  await page.selectOption('#summary-version-pick', version.file);
  await page.click('#summary-version-note');
  await page.waitForSelector('#note-dialog[open]');
  await page.fill('#note-text', '第一次的备注');
  await page.press('#note-text', 'Enter');
  await page.waitForFunction((file) => document.querySelector(`#summary-version-pick option[value="${file}"]`)?.textContent.includes('第一次的备注'), version.file);
  await page.click('#summary-version-note');
  assert.equal(await page.inputValue('#note-text'), '第一次的备注');
  await page.fill('#note-text', '改过的备注');
  await page.click('#note-dialog button[value=save]');
  await page.waitForFunction((file) => document.querySelector(`#summary-version-pick option[value="${file}"]`)?.textContent.includes('改过的备注'), version.file);
  assert.equal(listed().versions.find((entry) => entry.file === version.file).note, '改过的备注');
  const before = listed().current.note;
  await page.selectOption('#summary-version-pick', '');
  await page.click('#summary-version-note');
  await page.fill('#note-text', '当前这份');
  await page.click('#note-dialog button[value=cancel]');
  assert.equal(listed().current.note, before);
});

devTest('a folder for a chat AI holds the prompt and pictures within the file limit', async () => {
  await page.check('input[name=route][value=copy]');
  await page.fill('#export-limit', '3');
  const parent = path.join(ROOT, 'exports');
  fs.mkdirSync(parent);
  await app.evaluate(({ dialog, shell }, folder) => {
    const [open, reveal] = [dialog.showOpenDialog, shell.showItemInFolder];
    globalThis.vaRestoreDialogs = () => Object.assign(dialog, { showOpenDialog: open }) && Object.assign(shell, { showItemInFolder: reveal });
    dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [folder] });
    shell.showItemInFolder = () => {}; // no Explorer window
  }, parent);
  await page.click('#export-folder');
  await page.waitForFunction(() => document.querySelector('#summary-state').textContent.includes('已导出到'));
  await app.evaluate(() => globalThis.vaRestoreDialogs());
  const [folder] = fs.readdirSync(parent);
  assert.equal(fs.readdirSync(path.join(parent, folder)).length, 3);
  assert.ok(fs.existsSync(path.join(parent, folder, '提示词.md')));
});

devTest('a collection lists its videos and copies the material for its overview', async () => {
  await page.click('#new-collection');
  await page.fill('#collection-dialog-name', '测试合集');
  await page.click('#collection-dialog button[value=save]');
  await page.waitForSelector('#collection:not([hidden]) #collection-name:text("测试合集")');
  assert.equal(await page.isDisabled('#collection-add'), true, 'nothing chosen yet');
  await page.selectOption('#collection-add-choice', { index: 1 }); // 0 is the prompt
  await page.click('#collection-add');
  await page.waitForSelector('#collection-members .member .badge:text("已总结")');
  assert.match(await page.textContent('#collection-list'), /测试合集1 集/);
  await page.selectOption('#collection-route', 'copy');
  await page.click('#collection-overview');
  await page.waitForFunction(() => document.querySelector('#collection-state').textContent.includes('已复制'));
  const copied = await app.evaluate(({ clipboard }) => clipboard.readText());
  assert.match(copied, /为合集「测试合集」写 合集总结\.md/);
  assert.match(copied, /# 测试视频/);
  // Following a list keeps its link for later checks; nothing is downloaded until 检查新视频.
  assert.equal(await page.isVisible('#collection-follow-form'), true);
  await page.fill('#collection-follow-url', 'https://example.com/list');
  await page.click('#collection-follow-form button[type=submit]');
  await page.waitForSelector('#collection-following:not([hidden])');
  assert.match(await page.textContent('#collection-source-info'), /example\.com\/list.*还没检查过/);
  await page.click('#collection-auto');
  await page.waitForFunction(() => document.querySelector('#collection-state').textContent === '');
  assert.equal(JSON.parse(cli(['collection', 'show', '测试合集', '-o', WORKSPACE])).source.auto, true);
  // 压缩各集 asks before replacing files that are not this program's downloads; dismissed, it compresses none.
  await refuse(true);
  await page.click('#collection-compress-all');
  await page.waitForFunction(() => document.querySelector('#collection-state').textContent === '没有要压缩的。');
  await refuse(false);
  await page.click('#collection-unfollow');
  await page.waitForSelector('#collection-follow-form:not([hidden])');
  // A video in a collection is not under 视频 and not spread out in the sidebar: it opens from the collection's page,
  // which its page leads back to; taking it out brings it back under 视频.
  assert.equal(await page.$$eval('#video-list .video-item', (all) => all.length), 0);
  assert.equal(await page.$$eval('#collection-list .video-item', (all) => all.length), 1);
  await page.click('#collection-members .member .name');
  await page.waitForSelector('#video:not([hidden])');
  assert.equal(await page.isVisible('#collection-list .collection-item.active'), true, 'its collection is marked');
  assert.match(await page.textContent('#video-collection'), /测试合集 · 第 1 集/);
  // A list that cannot be read keeps what was shown and is read again (user report, 2026-10-29: one failed read put
  // every episode under 视频).
  const stored = path.join(WORKSPACE, '合集', '测试合集', 'collection.json');
  const good = fs.readFileSync(stored, 'utf8');
  fs.writeFileSync(stored, '{ broken');
  await page.evaluate(() => window.vaPage.loadCollections());
  await page.waitForSelector('#collection-list .collection-error');
  assert.equal(await page.$$eval('#collection-list .collection-item', (all) => all.length), 1, 'the collection stays');
  assert.equal(await page.$$eval('#video-list .video-item', (all) => all.length), 0, 'its video stays out of 视频');
  fs.writeFileSync(stored, good);
  await page.waitForSelector('#collection-list .collection-error', { state: 'detached', timeout: 15_000 });
  await page.click('#video-collection');
  await page.click('#collection-members .member button:text("移出")');
  await page.waitForSelector('#video-list .video-item');
  await page.click('#video-list .video-item');
  await page.waitForSelector('#video:not([hidden])');
  // Clicking the open video or collection again goes back to the start page (user request, 2026-10-29).
  await page.click('#video-list .video-item.active');
  await page.waitForSelector('#empty:not([hidden])');
  await page.click('#collection-list .collection-item');
  await page.waitForSelector('#collection:not([hidden])');
  await page.click('#collection-list .collection-item.active');
  await page.waitForSelector('#empty:not([hidden])');
  await page.click('#video-list .video-item');
  await page.waitForSelector('#video:not([hidden])');
});

test('settings list the summary templates, a new one shows on the summary page, and the skill reads only', async () => {
  await page.click('#open-settings');
  await page.waitForSelector('#rules-list .rules-row:has-text("标准"):has-text("正在用")');
  await page.waitForSelector('#rules-list .rules-row:has-text("命题分析")');
  assert.equal(await page.locator('#rules-list button:has-text("恢复自带的")').count(), 0);
  await app.evaluate(({ shell }) => {
    const open = shell.openPath;
    globalThis.vaRestoreDialogs = () => Object.assign(shell, { openPath: open });
    shell.openPath = async () => ''; // the new file would open in an editor
  });
  await page.fill('#rules-new-name', '测试模板');
  await page.selectOption('#rules-new-from', '命题分析');
  await page.click('#rules-new');
  await page.waitForSelector('#rules-list .rules-row:has-text("测试模板"):has-text("你自己的")');
  await page.waitForSelector('#route-template option[value="测试模板"]', { state: 'attached' });
  assert.match(cli(['template', '测试模板']), /论证结构/);
  await page.click('#rules-list .rules-row:has-text("测试模板") button:has-text("删除")');
  await page.waitForFunction(() => !document.querySelector('#route-template option[value="测试模板"]'));
  await app.evaluate(() => globalThis.vaRestoreDialogs());
  await page.click('#skill-view');
  await page.waitForSelector('#skill-dialog[open] #skill-text h2');
  assert.match(await page.textContent('#skill-text'), /A collection/);
  await page.click('#close-skill');
  await page.click('#settings button[value=cancel]');
});

devTest('the settings download AutoSlides Extractor\'s portable build into the data folder', async () => {
  // A release as GitHub's API gives it, with a zip holding the program in a folder, served from here.
  const files = path.join(ROOT, 'extractor-release');
  fs.mkdirSync(path.join(files, 'pack', 'AutoSlides Extractor'), { recursive: true });
  fs.writeFileSync(path.join(files, 'pack', 'AutoSlides Extractor', 'AutoSlidesExtractor.exe'), 'not a real program');
  const zip = path.join(files, 'AutoSlides.Extractor-9.9.9-Windows-x64-Portable.zip');
  execFileSync(path.join(process.env.SystemRoot, 'System32', 'tar.exe'), ['-a', '-cf', zip, '-C', path.join(files, 'pack'), 'AutoSlides Extractor'], { windowsHide: true });
  const bytes = fs.readFileSync(zip);
  const server = http.createServer((request, response) => {
    if (request.url === '/release') {
      const asset = {
        name: path.basename(zip),
        size: bytes.length,
        digest: 'sha256:' + require('node:crypto').createHash('sha256').update(bytes).digest('hex'),
        browser_download_url: `http://127.0.0.1:${server.address().port}/zip`,
      };
      response.end(JSON.stringify({ tag_name: 'v9.9.9', assets: [asset] }));
    } else response.end(bytes);
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  try {
    await app.evaluate((_, url) => (process.env.VA_EXTRACTOR_RELEASE = url), `http://127.0.0.1:${server.address().port}/release`);
    await page.click('#open-settings');
    await page.waitForSelector('#settings[open]');
    await page.click('#download-extractor');
    await page.waitForFunction(() => /已下载 v9\.9\.9|没有下载成功/.test(document.querySelector('#extractor-info').textContent));
    assert.match(await page.textContent('#extractor-info'), /已下载 v9\.9\.9/);
    const program = path.join(ROOT, 'gui-data', 'tools', 'AutoSlides Extractor', 'AutoSlides Extractor', 'AutoSlidesExtractor.exe');
    assert.equal(fs.readFileSync(program, 'utf8'), 'not a real program');
    await page.click('#close-settings');
  } finally {
    server.close();
  }
});

test('settings show the version, the licence and PRIVACY.md', async () => {
  await page.click('#open-settings');
  await page.waitForSelector('#settings[open]');
  await page.waitForFunction(() => /AGPL/.test(document.querySelector('#about-text').textContent));
  assert.match(await page.textContent('#about-text'), /Video Agent \d+\.\d+\.\d+/);
  assert.equal(await page.isVisible('#about-license'), true);
  await page.click('#about-privacy');
  await page.waitForSelector('#privacy-dialog[open] #privacy-text h2');
  const text = await page.textContent('#privacy-text');
  assert.match(text, /检查更新/);
  assert.doesNotMatch(text, /隐私和使用须知/); // the title is the dialog's, not repeated
  await page.click('#close-privacy');
  // The notices exist in a source tree only after a CLI build.
  if (process.env.VA_E2E_EXE) assert.equal(await page.isVisible('#about-notices'), true);
  await page.click('#settings button[value=cancel]');
  if (!process.env.VA_E2E_EXE) return;
  // The installer's licence page: NSIS reads it as UTF-8 only after a byte order mark, and wants CRLF line ends.
  const licencePage = fs.readFileSync(path.join(path.dirname(process.env.VA_E2E_EXE), 'PRIVACY.txt'));
  assert.deepEqual([...licencePage.subarray(0, 3)], [0xef, 0xbb, 0xbf]);
  assert.doesNotMatch(licencePage.toString('utf8'), /[^\r]\n/);
  assert.match(licencePage.toString('utf8'), /【隐私】/);
});

test('settings dialog saves the model through the CLI', async () => {
  const keyBefore = JSON.parse(cli(['config', '--json', '--provider', 'openai'])).key;
  await page.click('#open-settings');
  await page.waitForSelector('#settings[open]');
  await page.waitForFunction(() => document.querySelector('#set-model').value === 'fake-model');
  if (process.env.VA_E2E_EXE) assert.match(await page.textContent('#env-info'), /安装程序自带的 video-agent/);
  await page.fill('#set-model', 'fake-model-2');
  if (!keyBefore) await page.fill('#set-key', 'e2e-test-key');
  await page.click('#save-settings');
  await page.waitForFunction(() => !document.querySelector('#settings').open);
  let shown;
  for (let i = 0; i < 40 && shown?.model !== 'fake-model-2'; i++) {
    await new Promise((resolve) => setTimeout(resolve, 250));
    shown = JSON.parse(cli(['config', '--json']));
  }
  assert.equal(shown.model, 'fake-model-2');
  if (!keyBefore) {
    assert.equal(shown.key, 'Credential Manager');
    cli(['config', '--provider', 'openai', '--delete-key']);
  }
});

devTest('settings close at once without changes and ask first with them', async () => {
  const shown = () => page.$eval('#settings', (dialog) => dialog.open);
  await page.click('#open-settings');
  await page.waitForSelector('#settings[open]');
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => !document.querySelector('#settings').open);
  await page.click('#open-settings');
  await page.waitForSelector('#settings[open]');
  const limit = await page.inputValue('#set-limit-download');
  await page.fill('#set-limit-download', String(Number(limit) + 1));
  await page.click('#close-settings');
  assert.equal(await shown(), true);
  assert.equal(await page.isVisible('#settings-unsaved'), true);
  await page.click('#discard-settings');
  await page.waitForFunction(() => !document.querySelector('#settings').open);
  await page.click('#open-settings');
  await page.waitForSelector('#settings[open]');
  assert.equal(await page.inputValue('#set-limit-download'), limit, 'the change was dropped');
  await page.mouse.click(5, 5); // outside the dialog
  await page.waitForFunction(() => !document.querySelector('#settings').open);
});

devTest('logs record every job and never the API key', async () => {
  await page.click('#open-logs');
  await page.waitForSelector('#logs[open] .log-entry');
  const titles = await page.locator('.log-entry').allTextContents();
  assert.ok(titles.some((text) => /处理：sample clip \[e2e\]\.mp4.*完成/.test(text)), titles.join(' | '));
  assert.ok(titles.some((text) => text.includes('总结（模型 API · chosen-model · high）')));
  await page.locator('.log-entry', { hasText: '处理：' }).first().click(); // newest of the two processing runs
  await page.waitForFunction(() => document.querySelector('#log-view').textContent.includes('evidence saved'));
  await page.click('#close-logs');

  const dir = path.join(ROOT, 'gui-data', 'logs');
  const files = [path.join(dir, 'main.log'), ...fs.readdirSync(path.join(dir, 'jobs')).map((name) => path.join(dir, 'jobs', name))];
  const all = files.map((file) => fs.readFileSync(file, 'utf8')).join('\n');
  assert.match(all, /job task-[\w-]+ started: 处理/);
  assert.doesNotMatch(all, /e2e-test-key/);
});

test('closing the window keeps the app in the tray', async () => {
  const labels = await app.evaluate(() => global.vaTray.labels());
  for (const label of ['显示窗口', '添加本地视频…', '打开日志文件夹', '退出']) assert.ok(labels.includes(label), label);
  assert.equal(await app.evaluate(() => global.vaTray.tooltip()), 'Video Agent');
  // The main window, not DeepSeek's, which an earlier test opened.
  await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows().find((win) => win.getTitle() !== 'DeepSeek').close());
  assert.equal(await app.evaluate(() => global.vaTray.windowVisible()), false);
  await app.evaluate(() => global.vaTray.click('显示窗口'));
  assert.equal(await app.evaluate(() => global.vaTray.windowVisible()), true);
});

test('embedded terminal runs a command in the video folder', async () => {
  await page.click('.tabs button[data-tab=terminal]');
  // Nothing starts until asked for.
  await page.waitForSelector('#terminal .terminal-note');
  assert.equal(await page.locator('.xterm-rows').count(), 0);
  assert.equal(await page.textContent('#new-terminal'), '启动终端');
  await page.click('#new-terminal');
  await page.waitForSelector('.xterm-rows');
  assert.equal(await page.textContent('#new-terminal'), '新建终端');
  await page.waitForFunction(() => document.querySelector('.xterm-rows').textContent.includes('>'), null, { timeout: 30_000 });
  await page.click('#terminal');
  await page.keyboard.type('echo va-e2e-%CD%');
  await page.keyboard.press('Enter');
  await page.waitForFunction(
    () => /va-e2e-.*sample-clip/.test(document.querySelector('.xterm-rows').textContent.replace(/\s+/g, '')),
    null,
    { timeout: 30_000 },
  );
  if (!process.env.VA_E2E_EXE) return;
  // The packaged app puts its bundled CLI first on the terminal's PATH.
  await page.keyboard.type('where video-agent');
  await page.keyboard.press('Enter');
  await page.waitForFunction(
    () => /resources\\cli\\video-agent\.exe/i.test(document.querySelector('.xterm-rows').textContent.replace(/\s+/g, '')),
    null,
    { timeout: 30_000 },
  );
});

test('a site login is exported as a Netscape cookies file for yt-dlp', async () => {
  const file = path.join(ROOT, 'cookies', 'bilibili.txt');
  const written = await app.evaluate(async ({ session }, file) => {
    const store = session.fromPartition('persist:bilibili');
    const expirationDate = Math.floor(Date.now() / 1000) + 3600;
    const url = 'https://www.bilibili.com/';
    await store.cookies.set({ url, domain: '.bilibili.com', name: 'SESSDATA', value: 'login', httpOnly: true, secure: true, expirationDate });
    await store.cookies.set({ url, name: 'buvid3', value: 'host-only', expirationDate });
    await store.cookies.set({ url: 'https://example.com/', name: 'other', value: 'elsewhere', expirationDate });
    const result = await global.vaAccounts.writeCookies('bilibili', file);
    await store.clearStorageData();
    return [result, await global.vaAccounts.writeCookies('bilibili', `${file}.after-logout`)];
  }, file);
  assert.deepEqual(written, [file, null]);
  const lines = fs.readFileSync(file, 'utf8').trim().split('\n');
  assert.equal(lines[0], '# Netscape HTTP Cookie File');
  assert.ok(lines.some((line) => /^#HttpOnly_\.bilibili\.com\tTRUE\t\/\tTRUE\t\d+\tSESSDATA\tlogin$/.test(line)), lines.join(' | '));
  assert.ok(lines.some((line) => /^www\.bilibili\.com\tFALSE\t\/\tFALSE\t\d+\tbuvid3\thost-only$/.test(line)), lines.join(' | '));
  assert.ok(!lines.some((line) => line.includes('elsewhere')));
});

devTest('accounts are listed in an order of one\'s own, can be hidden, and take an imported cookies.txt', async () => {
  const names = () => page.$$eval('#accounts .account-name', (all) => all.map((item) => item.textContent));
  await page.click('#open-settings');
  await page.waitForSelector('#settings[open] #accounts .account');
  assert.deepEqual(await names(), ['哔哩哔哩', '抖音', 'YouTube']);
  await page.click('#accounts .account[data-account=youtube] button[title=往前]');
  await page.waitForFunction(() => document.querySelector('#accounts .account:nth-child(2)')?.dataset.account === 'youtube');
  await page.click('#accounts .account[data-account=douyin] button:text("隐藏")');
  await page.waitForSelector('#accounts-hidden:not([hidden]) a:text("抖音")');
  assert.deepEqual(await names(), ['哔哩哔哩', 'YouTube']);
  assert.deepEqual((await page.evaluate(() => window.va.settings())).accountOrder, ['bilibili', 'youtube', 'douyin']);
  await page.click('#accounts-hidden a:text("抖音")');
  await page.waitForFunction(() => document.querySelectorAll('#accounts .account').length === 3);
  // A cookies.txt from a browser, for when Google will not sign in here: only the site's own cookies are kept.
  const exported = path.join(ROOT, 'youtube-cookies.txt');
  const later = Math.floor(Date.now() / 1000) + 3600;
  fs.writeFileSync(exported, ['# Netscape HTTP Cookie File',
    `.youtube.com\tTRUE\t/\tTRUE\t${later}\tSAPISID\tfrom-browser`,
    `#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t${later}\tLOGIN_INFO\tsecret`,
    `.google.com\tTRUE\t/\tTRUE\t${later}\tSID\tnot-for-youtube`, ''].join('\n'));
  await app.evaluate(({ dialog }, chosen) => {
    const open = dialog.showOpenDialog;
    globalThis.vaRestoreDialogs = () => Object.assign(dialog, { showOpenDialog: open });
    dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [chosen] });
  }, exported);
  await page.click('#accounts .account[data-account=youtube] button:text("从浏览器导入…")');
  await page.waitForSelector('#cookie-dialog[open] #cookie-home:text("https://www.youtube.com/")');
  await page.click('#cookie-file');
  await page.waitForSelector('#cookie-state:text("导入了 2 条YouTube的 Cookie")');
  await page.waitForSelector('#accounts .account[data-account=youtube] .account-state:text("已登录")');
  await app.evaluate(() => globalThis.vaRestoreDialogs());
  await page.click('#cookie-dialog button[value=close]');
  const file = path.join(ROOT, 'cookies', 'youtube.txt');
  await app.evaluate(({}, file) => global.vaAccounts.writeCookies('youtube', file), file);
  const text = fs.readFileSync(file, 'utf8');
  assert.match(text, /\.youtube\.com\tTRUE\t\/\tTRUE\t\d+\tSAPISID\tfrom-browser/);
  assert.match(text, /#HttpOnly_\.youtube\.com\t.*LOGIN_INFO\tsecret/);
  assert.doesNotMatch(text, /not-for-youtube/);
  await page.click('#accounts .account[data-account=youtube] button:text("退出登录")');
  await page.waitForSelector('#accounts .account[data-account=youtube] .account-state:text("没有登录")');
  await page.click('#close-settings');
  // The hint under the link names what a link from such a site needs.
  await page.fill('#download-url', 'https://www.douyin.com/video/7300000000000000000');
  await page.waitForSelector('#download-hint:not([hidden]) #download-login:text("打开")');
  await page.fill('#download-url', 'https://www.youtube.com/watch?v=abc');
  await page.waitForSelector('#download-hint', { state: 'hidden' });
  await page.fill('#download-url', '');
});

devTest('a subtitle file of another name replaces the transcript', async () => {
  const file = path.join(ROOT, 'teacher.vtt');
  fs.writeFileSync(file, 'WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n老师给的字幕\n');
  await app.evaluate(({ dialog }, chosen) => {
    const open = dialog.showOpenDialog;
    globalThis.vaRestoreDialogs = () => Object.assign(dialog, { showOpenDialog: open });
    dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [chosen] });
  }, file);
  await page.click('.tabs button[data-tab=transcript]');
  await page.fill('#transcript-filter', '');
  await page.click('#import-subtitles');
  await page.waitForFunction(() => document.querySelector('#transcript').textContent.includes('老师给的字幕'), null, {
    timeout: 60_000,
  });
  await app.evaluate(() => globalThis.vaRestoreDialogs());
  assert.equal(JSON.parse(cli(['show', VIDEO, '-o', WORKSPACE])).manifest.transcript.source, 'file:teacher.vtt');
});

devTest('a folder of slide images is taken and placed by the screen pages', async () => {
  const folder = path.join(ROOT, '课件');
  fs.mkdirSync(folder);
  execFileSync('ffmpeg', ['-v', 'error', '-y', '-ss', '6', '-i', VIDEO, '-frames:v', '1', path.join(folder, 'page.png')]);
  await app.evaluate(({ dialog }, chosen) => {
    const open = dialog.showOpenDialog;
    globalThis.vaRestoreDialogs = () => Object.assign(dialog, { showOpenDialog: open });
    dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [chosen] });
  }, folder);
  await page.click('.tabs button[data-tab=frames]');
  await page.click('#import-slides');
  await page.waitForSelector('#pages-title:text("课件（1）")', { timeout: 60_000 });
  await app.evaluate(() => globalThis.vaRestoreDialogs());
});

devTest('remove the video from the list', async () => {
  await page.click('#remove-video');
  await page.waitForSelector('#empty:not([hidden])');
  assert.equal(await page.locator('#video-list .video-item').count(), 0);
});

devTest('added local videos are processed at once, and those without subtitles are asked about first', async () => {
  const folder = path.join(ROOT, 'local');
  fs.mkdirSync(folder);
  const withSubs = path.join(folder, 'with subs.mp4');
  const bare = path.join(folder, 'bare.mp4');
  fs.copyFileSync(VIDEO, withSubs);
  fs.copyFileSync(VIDEO.replace(/\.mp4$/, '.srt'), withSubs.replace(/\.mp4$/, '.srt'));
  fs.copyFileSync(VIDEO, bare);
  await app.evaluate(({ dialog }, chosen) => {
    const open = dialog.showOpenDialog;
    globalThis.vaRestoreDialogs = () => Object.assign(dialog, { showOpenDialog: open });
    dialog.showOpenDialog = async () => ({ canceled: false, filePaths: chosen });
  }, [withSubs, bare]);
  await page.click('#add-videos');
  await page.waitForSelector('#nosubs-dialog[open]');
  await app.evaluate(() => globalThis.vaRestoreDialogs());
  assert.equal(await page.textContent('#nosubs-list'), 'bare.mp4');
  await page.click('#nosubs-dialog button[value=later]');
  await page.waitForSelector('#video-list .video-item:has-text("with subs") .badge:text("已处理")', { timeout: 60_000 });
  assert.match(await page.textContent('#video-list .video-item:has-text("bare")'), /未处理/);
});

devTest('ticked tasks stop together, and 全部停止 stops the rest', async () => {
  const waiting = path.join(ROOT, 'waiting-agent.js');
  fs.writeFileSync(waiting, 'setTimeout(() => {}, 120_000);\n');
  await page.click('#open-settings');
  await page.waitForSelector('#settings[open]');
  await page.check('#set-agents input[data-agent=custom]');
  await page.fill('#set-agents input[data-agent-command=custom]', `"${process.execPath}" "${waiting}"`);
  await page.click('#save-settings');
  await page.waitForSelector('#settings[open]', { state: 'hidden' });
  // Saved once the agent shows as a route; tasks queued before that would not find it.
  await saved((settings) => settings.agents?.some((agent) => agent.key === 'custom' && /waiting-agent/.test(agent.command)));
  // Summaries of three videos by an agent that only waits: two run (the default limit), the third is queued.
  const videos = ['甲', '乙', '丙'].map((name) => path.join(ROOT, `${name}.mp4`));
  await page.evaluate((all) => Promise.all(all.map((video, i) => window.va.addTask({
    kind: 'summary', route: 'custom', agent: 'custom', title: `等待${'甲乙丙'[i]}`, video, folder: video,
  }))), videos);
  if (await page.isHidden('#log')) await page.click('#open-tasks');
  const item = (name) => `#task-list .task-item:has-text("等待${name}")`;
  const states = () => page.evaluate(async () => {
    const tasks = (await window.va.tasks()).filter((task) => task.title.startsWith('等待'));
    const outputs = await Promise.all(tasks.map((task) => window.va.taskOutput(task.id)));
    return tasks.map((task, i) => `${task.title} ${task.status}: ${JSON.stringify(outputs[i]).slice(0, 400)}`).join('\n');
  });
  try {
    await page.waitForSelector(`${item('乙')} .badge:text("运行中")`, { timeout: 15_000 });
  } catch (error) {
    assert.fail(`等待乙 is not running:\n${await states()}\n${error.message}`);
  }
  assert.equal(await page.isDisabled('#stop-all'), false);
  assert.equal(await page.isHidden('#stop-picked'), true, 'nothing ticked yet');
  await page.check(`${item('甲')} .pick`);
  await page.check(`${item('丙')} .pick`);
  assert.equal(await page.textContent('#stop-picked'), '停止所选（2）');
  await page.click('#stop-picked');
  await page.waitForSelector(`${item('甲')} .badge:text("已停止")`);
  await page.waitForSelector(`${item('丙')} .badge:text("已停止")`);
  assert.equal(await page.textContent(`${item('乙')} .badge`), '运行中', 'the one not ticked goes on');
  await page.click('#stop-all'); // its confirm() is accepted
  await page.waitForSelector(`${item('乙')} .badge:text("已停止")`);
  assert.equal(await page.isDisabled('#stop-all'), true);
  assert.equal(await page.$$eval('#task-list .pick', (all) => all.length), 0);
});

test('the skill is copied into a picked folder, but never over another folder of that name', async () => {
  const picked = path.join(ROOT, 'skills-home');
  const other = path.join(ROOT, 'has-a-project');
  fs.mkdirSync(path.join(other, 'video-agent'), { recursive: true });
  fs.writeFileSync(path.join(other, 'video-agent', 'pyproject.toml'), '');
  const pick = (folder) => app.evaluate(({ dialog }, chosen) => {
    globalThis.vaRestoreDialogs?.(); // the real one, not the stub of the pick before
    const open = dialog.showOpenDialog;
    globalThis.vaRestoreDialogs = () => Object.assign(dialog, { showOpenDialog: open });
    dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [chosen] });
  }, folder);
  await page.click('#open-settings');
  await page.waitForSelector('#settings[open]');
  await pick(picked);
  await page.click('#skill-targets button[data-skill=folder]');
  await page.waitForFunction(() => /已复制到/.test(document.querySelector('#plugin-output').textContent));
  assert.ok(fs.existsSync(path.join(picked, 'video-agent', 'SKILL.md')));
  await page.click('#skill-targets button[data-skill=folder]'); // again: the earlier copy is replaced
  await page.waitForFunction(() => /已复制到/.test(document.querySelector('#plugin-output').textContent));
  await pick(other);
  await page.click('#skill-targets button[data-skill=folder]');
  await page.waitForFunction(() => /不是之前复制的 skill，没有动它/.test(document.querySelector('#plugin-output').textContent));
  assert.ok(fs.existsSync(path.join(other, 'video-agent', 'pyproject.toml')), 'the other folder is left alone');
  await app.evaluate(() => globalThis.vaRestoreDialogs());
  await page.click('#close-settings');
});
