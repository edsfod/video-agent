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
const ENV = { ...process.env, APPDATA, NO_PROXY: '127.0.0.1,localhost', no_proxy: '127.0.0.1,localhost' };
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

let app;
let page;
let model;

test.before(async () => {
  makeVideo();
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
  page.on('dialog', (dialog) => dialog.accept());
  await page.waitForSelector('#video-list .video-item .badge:text("未处理")');
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
  assert.match(facts, /2 段 · 字幕文件：sample clip \[e2e\]\.srt/);
  assert.match(facts, /布局整个画面是屏幕/);
  await page.waitForSelector('#layout-card:not([hidden]) #layout-image');
  assert.match(await page.textContent('#log-text'), /完成/);
});

test('the same processing is queued once, and the queue empties when it ends', async () => {
  await Promise.all([page.click('#run-process'), page.click('#run-process')]);
  await page.waitForFunction(() => document.querySelector('#task-note').textContent.includes('已经在队列里'));
  assert.equal(await page.locator('.task-item', { hasText: '处理：' }).count(), 2); // the first run and this one
  await page.waitForFunction(() => document.querySelector('#open-tasks').textContent === '任务', null, { timeout: 60_000 });
  await page.waitForSelector('#video-list .video-item .badge:text("已处理")');
});

test('transcript tab lists the lines', async () => {
  await page.click('.tabs button[data-tab=transcript]');
  await page.waitForSelector('#transcript .line');
  assert.equal(await page.locator('#transcript .line').count(), 2);
  await page.fill('#transcript-filter', '图表');
  await page.waitForFunction(() => document.querySelectorAll('#transcript .line').length === 1);
});

test('a correction gives a cleaned transcript and keeps the original', async () => {
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

test('frames tab takes an extra frame', async () => {
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
  await page.check('input[name=route][value=api]');
  await page.click('#run-summary');
  await page.waitForSelector('#summary h1:text("测试视频")', { timeout: 60_000 });
  assert.equal(model.requests.length, 2);
  assert.equal(model.requests[0].tools[0].function.name, 'frame');
  assert.equal(model.requests[1].messages.at(-1).content[1].type, 'image_url');
  await page.waitForSelector('#video-list .video-item .badge:text("已总结")');
  await page.click('#summary a');
  await page.waitForSelector('#lightbox[open]');
  await page.click('#lightbox');
});

test('copy material puts the rules and transcript on the clipboard', async () => {
  await page.check('input[name=route][value=copy]');
  await page.click('#run-summary');
  await page.waitForFunction(() => document.querySelector('#summary-state').textContent.includes('已复制'));
  const copied = await app.evaluate(({ clipboard }) => clipboard.readText());
  assert.match(copied, /# Writing a video summary/);
  assert.match(copied, /我们看看这张图表/);
});

test('a collection lists its videos and copies the material for its overview', async () => {
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
  await page.click('#collection-unfollow');
  await page.waitForSelector('#collection-follow-form:not([hidden])');
  await page.click('#video-list .video-item');
  await page.waitForSelector('#video:not([hidden])');
});

test('settings show which summary rules are in use and the skill read-only', async () => {
  await page.click('#open-settings');
  await page.waitForFunction(() => document.querySelector('#rules-status').textContent === '正在用默认规则。');
  assert.equal(await page.isHidden('#rules-reset'), true);
  await page.click('#skill-view');
  await page.waitForSelector('#skill-dialog[open] #skill-text h2');
  assert.match(await page.textContent('#skill-text'), /Summarize a video/);
  await page.click('#close-skill');
  await page.click('#settings button[value=cancel]');
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

test('settings close at once without changes and ask first with them', async () => {
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

test('logs record every job and never the API key', async () => {
  await page.click('#open-logs');
  await page.waitForSelector('#logs[open] .log-entry');
  const titles = await page.locator('.log-entry').allTextContents();
  assert.ok(titles.some((text) => /处理：sample clip \[e2e\]\.mp4.*完成/.test(text)), titles.join(' | '));
  assert.ok(titles.some((text) => text.includes('总结（模型 API）')));
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
  await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].close());
  assert.equal(await app.evaluate(() => global.vaTray.windowVisible()), false);
  await app.evaluate(() => global.vaTray.click('显示窗口'));
  assert.equal(await app.evaluate(() => global.vaTray.windowVisible()), true);
});

test('embedded terminal runs a command in the video folder', async () => {
  await page.click('.tabs button[data-tab=terminal]');
  await page.waitForSelector('.xterm-rows');
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

test('the Bilibili login is exported as a Netscape cookies file for yt-dlp', async () => {
  const file = path.join(ROOT, 'cookies', 'bilibili.txt');
  const written = await app.evaluate(async ({ session }, file) => {
    const store = session.fromPartition('persist:bilibili');
    const expirationDate = Math.floor(Date.now() / 1000) + 3600;
    const url = 'https://www.bilibili.com/';
    await store.cookies.set({ url, domain: '.bilibili.com', name: 'SESSDATA', value: 'login', httpOnly: true, secure: true, expirationDate });
    await store.cookies.set({ url, name: 'buvid3', value: 'host-only', expirationDate });
    await store.cookies.set({ url: 'https://example.com/', name: 'other', value: 'elsewhere', expirationDate });
    const result = await global.vaBilibili.writeCookies(file);
    await store.clearStorageData();
    return [result, await global.vaBilibili.writeCookies(`${file}.after-logout`)];
  }, file);
  assert.deepEqual(written, [file, null]);
  const lines = fs.readFileSync(file, 'utf8').trim().split('\n');
  assert.equal(lines[0], '# Netscape HTTP Cookie File');
  assert.ok(lines.some((line) => /^#HttpOnly_\.bilibili\.com\tTRUE\t\/\tTRUE\t\d+\tSESSDATA\tlogin$/.test(line)), lines.join(' | '));
  assert.ok(lines.some((line) => /^www\.bilibili\.com\tFALSE\t\/\tFALSE\t\d+\tbuvid3\thost-only$/.test(line)), lines.join(' | '));
  assert.ok(!lines.some((line) => line.includes('elsewhere')));
});

test('remove the video from the list', async () => {
  await page.click('#remove-video');
  await page.waitForSelector('#empty:not([hidden])');
  assert.equal(await page.locator('#video-list .video-item').count(), 0);
});
