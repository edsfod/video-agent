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
const ENV = { ...process.env, VA_E2E_BACKGROUND: '1', APPDATA, NO_PROXY: '127.0.0.1,localhost', no_proxy: '127.0.0.1,localhost' };
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
// Every confirm() is accepted unless a test asks for the other answer.
let refuse = false;
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
  page.on('dialog', (dialog) => (refuse ? dialog.dismiss() : dialog.accept()));
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
  assert.match(facts, /2 段 · 同名字幕文件/); // the file name, long for downloads, only as the card's tooltip
  assert.equal(await page.getAttribute('#facts .fact:nth-child(2)', 'title'), 'sample clip [e2e].srt');
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
  assert.equal(await page.getAttribute('#routes label:first-child input', 'value'), 'copy', '复制材料 comes first');
  await page.check('input[name=route][value=api]');
  // A model chosen on the page for this route, instead of the one in the settings.
  await page.fill('#route-model', 'chosen-model');
  await page.press('#route-model', 'Tab');
  await page.waitForFunction(async () => (await window.va.settings()).routeModels?.api === 'chosen-model');
  await page.click('#run-summary');
  await page.waitForSelector('#summary h1:text("测试视频")', { timeout: 60_000 });
  assert.equal(model.requests[0].model, 'chosen-model');
  assert.equal(await page.isHidden('#route-model-label'), false);
  await page.fill('#route-model', '');
  await page.press('#route-model', 'Tab');
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
const draft = path.join(workspace, 'draft.md');
fs.writeFileSync(draft, '# 别的 Agent 写的\\n\\n## 概要\\n\\n这是另一个 Agent 按 skill 写的测试总结，任务来自' + (file ? '文件' : '标准输入') + '。\\n');
execFileSync('video-agent', ['summarize', video, '-o', workspace, '--import', draft, '--source', /--source "([^"]+)"/.exec(task)[1]]);
fs.rmSync(draft);
`;

test('another agent writes a summary from standard input or from a task file', async () => {
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
  // Several at once: each ticked agent is a route of its own; one whose command is not here shows but cannot be chosen.
  await page.click('#open-settings');
  await page.check('#set-agents input[data-agent=dsh]');
  await page.fill('#set-agents input[data-agent-command=dsh]', 'va-e2e-no-such-agent {prompt}');
  await page.click('#save-settings');
  await page.waitForSelector('#routes .route-agent:has-text("DeepSeek Harness")');
  assert.equal(await page.isDisabled('input[name=route][value=dsh]'), true);
  assert.equal(await page.isDisabled('input[name=route][value=custom]'), false);
  await page.click('#open-settings');
  await page.uncheck('#set-agents input[data-agent=custom]');
  await page.uncheck('#set-agents input[data-agent=dsh]');
  await page.click('#save-settings');
  await page.waitForSelector('#routes .route-agent:has-text("其他 Agent")');
  // With none chosen it still shows, says where to choose one, and writes nothing.
  await page.check('input[name=route][value=other]');
  assert.match(await page.textContent('#route-note'), /设置.*其他 Agent/);
  assert.equal(await page.isDisabled('#run-summary'), true);
  await page.check('input[name=route][value=api]');
});

test('a version note is edited in a dialog that starts from the note it has', async () => {
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

test('a folder for a chat AI holds the prompt and pictures within the file limit', async () => {
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
  // 压缩各集 asks before replacing files that are not this program's downloads; dismissed, it compresses none.
  refuse = true;
  await page.click('#collection-compress-all');
  await page.waitForFunction(() => document.querySelector('#collection-state').textContent === '没有要压缩的。');
  refuse = false;
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
  await page.click('#video-collection');
  await page.click('#collection-members .member button:text("移出")');
  await page.waitForSelector('#video-list .video-item');
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

test('a subtitle file of another name replaces the transcript', async () => {
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

test('a folder of slide images is taken and placed by the screen pages', async () => {
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

test('remove the video from the list', async () => {
  await page.click('#remove-video');
  await page.waitForSelector('#empty:not([hidden])');
  assert.equal(await page.locator('#video-list .video-item').count(), 0);
});

test('added local videos are processed at once, and those without subtitles are asked about first', async () => {
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

test('ticked tasks stop together, and 全部停止 stops the rest', async () => {
  const waiting = path.join(ROOT, 'waiting-agent.js');
  fs.writeFileSync(waiting, 'setTimeout(() => {}, 120_000);\n');
  await page.click('#open-settings');
  await page.waitForSelector('#settings[open]');
  await page.check('#set-agents input[data-agent=custom]');
  await page.fill('#set-agents input[data-agent-command=custom]', `"${process.execPath}" "${waiting}"`);
  await page.click('#save-settings');
  await page.waitForSelector('#settings[open]', { state: 'hidden' });
  // Saved once the agent shows as a route; tasks queued before that would not find it.
  await page.waitForFunction(async () => (await window.va.settings()).agents?.some((agent) => agent.key === 'custom' && /waiting-agent/.test(agent.command)));
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
