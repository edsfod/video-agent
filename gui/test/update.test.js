// End-to-end test of checking for and downloading an update, against a local fake release feed signed with a test
// key: a tampered latest.yml is refused, a dead source is skipped, a source that serves the installer too slowly is
// left for the next one, and a good update downloads and passes the sha512 check. Installing is covered by update-install.test.js on an installed build.

const test = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const { _electron: electron } = require('playwright-core');
const signature = require('../src/update-signature');

const GUI = path.resolve(__dirname, '..');
const ROOT = fs.mkdtempSync(path.join(os.tmpdir(), 'va-update-'));
// The packaged app's cache, or the separate one dev-app-update.yml names for the unpackaged app.
const CACHE = path.join(process.env.LOCALAPPDATA, process.env.VA_E2E_EXE ? 'video-agent-gui-updater' : 'video-agent-gui-updater-dev');
const cacheExisted = fs.existsSync(CACHE);
const { privateKey, publicKey } = crypto.generateKeyPairSync('ed25519');
const PUBLIC = publicKey.export({ type: 'spki', format: 'der' }).toString('base64');
const PRIVATE = privateKey.export({ type: 'pkcs8', format: 'pem' });

const VERSION = '9.9.9';
const INSTALLER = crypto.randomBytes(256 * 1024);
const NAME = `Video-Agent-Setup-${VERSION}.exe`;
const latest = [
  `version: ${VERSION}`,
  'files:',
  `  - url: ${NAME}`,
  `    sha512: ${crypto.createHash('sha512').update(INSTALLER).digest('base64')}`,
  `    size: ${INSTALLER.length}`,
  `path: ${NAME}`,
  `sha512: ${crypto.createHash('sha512').update(INSTALLER).digest('base64')}`,
  "releaseDate: '2026-10-27T00:00:00.000Z'",
  "releaseNotes: '## 测试更新\n\n- 一条说明'",
  '',
].join('\n');

let tampered = true;
const served = [];
const server = http.createServer((request, response) => {
  served.push(request.url);
  const file = request.url.split('?')[0].split('/').pop();
  const body = {
    'latest.yml': tampered ? latest.replace('一条说明', '被改过的说明') : latest,
    'latest.yml.sig': signature.sign(latest, PRIVATE),
    [NAME]: INSTALLER,
  }[file];
  if (body === undefined) return (response.statusCode = 404), response.end();
  if (!(request.url.startsWith('/slow/') && file === NAME)) return response.end(body);
  // Under /slow/ the installer comes at 8 KB/s, which would take half a minute.
  response.setHeader('Content-Length', body.length);
  let sent = 0;
  const timer = setInterval(() => {
    response.write(body.subarray(sent, (sent += 2048)));
    if (sent >= body.length) clearInterval(timer), response.end();
  }, 250);
  response.on('close', () => clearInterval(timer));
});

let app;
let page;
const base = () => `http://127.0.0.1:${server.address().port}`;

test.before(async () => {
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const dead = http.createServer();
  await new Promise((resolve) => dead.listen(0, '127.0.0.1', resolve));
  const deadPort = dead.address().port;
  dead.close(); // a port nothing answers on, as the first source
  const userData = path.join(ROOT, 'gui-data');
  fs.mkdirSync(userData, { recursive: true });
  fs.writeFileSync(path.join(userData, 'settings.json'), JSON.stringify({ workspace: path.join(ROOT, 'workspace'), videos: [] }));
  const packaged = process.env.VA_E2E_EXE;
  app = await electron.launch({
    executablePath: packaged || require('electron'),
    args: [...(packaged ? [] : ['.']), `--user-data=${userData}`],
    cwd: GUI,
    env: {
      ...process.env,
      VA_UPDATE_ROOT: [`http://127.0.0.1:${deadPort}/releases`, `${base()}/slow/releases`, `${base()}/releases`].join(','),
      VA_UPDATE_PUBLIC_KEY: PUBLIC,
      VA_UPDATE_DELAY_MS: '300',
      VA_UPDATE_SLOW: '3000,50000,2', // after 3 s, under 50 KB/s with more than 2 s to go
      NO_PROXY: '127.0.0.1,localhost',
      no_proxy: '127.0.0.1,localhost',
    },
  });
  page = await app.firstWindow();
});

test.after(async () => {
  await app?.close();
  server.close();
  // The download lands in electron-updater's cache; leave the folder as it was.
  fs.rmSync(cacheExisted ? path.join(CACHE, 'pending') : CACHE, { recursive: true, force: true });
});

const status = () => page.textContent('#update-status');

test('the startup check refuses a latest.yml that does not match its signature', async () => {
  await page.click('#open-settings');
  await page.waitForSelector('#settings[open]');
  await page.waitForFunction(() => /检查更新没有成功/.test(document.querySelector('#update-status').textContent), null, { timeout: 60_000 });
  assert.match(await status(), /测试源 1：/, 'the dead source is reported too');
  assert.match(await status(), /测试源 2：.*签名校验/);
  assert.equal(await page.isHidden('#update-download'), true);
  assert.ok(!served.some((url) => url.endsWith(NAME)), 'nothing was downloaded');
});

test('a signed update is offered with its notes, after skipping the dead source', async () => {
  tampered = false;
  await page.click('#update-check');
  await page.waitForFunction(() => /有新版本 9\.9\.9/.test(document.querySelector('#update-status').textContent), null, { timeout: 60_000 });
  assert.match(await page.textContent('#update-notes'), /测试更新/);
  assert.ok(served.includes('/slow/releases/latest/download/latest.yml'), 'the check is answered by the first live source');
  assert.equal(await page.isVisible('#update-download'), true);
  assert.ok(await page.$eval('#open-settings', (button) => button.classList.contains('has-update')));
});

test('a slow download moves to the next source, which fetches the installer from the versioned folder and checks its sha512', async () => {
  await page.click('#update-download');
  await page.waitForFunction(() => /测试源 2：太慢（约 \d+ KB\/s），换下一个/.test(document.querySelector('#update-status').textContent), null, { timeout: 30_000 });
  await page.waitForFunction(() => /已下载并通过校验/.test(document.querySelector('#update-status').textContent), null, { timeout: 120_000 });
  assert.ok(served.includes(`/slow/releases/download/v${VERSION}/${NAME}`), served.join(' '));
  assert.ok(served.includes(`/releases/download/v${VERSION}/${NAME}`), served.join(' '));
  assert.equal(await page.isVisible('#update-install'), true);
  const log = fs.readFileSync(path.join(ROOT, 'gui-data', 'logs', 'main.log'), 'utf8');
  assert.match(log, /update download via 测试源 2 failed: 太慢/);
  assert.match(log, /update 9\.9\.9 downloaded via 测试源 3/);
});
