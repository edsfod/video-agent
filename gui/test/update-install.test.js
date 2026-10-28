// End-to-end test of installing an update on an installed build (CI only: set VA_E2E_INSTALLED to its
// "Video Agent.exe"). The fake feed offers this same installer as 9.9.9, so the differential download should fetch
// next to nothing against the copy the installer left in the cache; then "重启并安装" must quit the app, run the
// installer silently and start the app again.

const test = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const { execFileSync, spawnSync } = require('node:child_process');
const yaml = require('js-yaml');
const { _electron: electron } = require('playwright-core');
const signature = require('../src/update-signature');

const INSTALLED = process.env.VA_E2E_INSTALLED;
const DIST = path.resolve(__dirname, '..', 'dist');
const NEW = '9.9.9';

function mainProcesses() {
  const script = "Get-CimInstance Win32_Process -Filter \"Name='Video Agent.exe'\" | " +
    "Where-Object { $_.CommandLine -notmatch '--type=' } | Select-Object ProcessId, ExecutablePath | ConvertTo-Json";
  const out = execFileSync('powershell.exe', ['-NoProfile', '-Command', script], { encoding: 'utf8' }).trim();
  return out ? [].concat(JSON.parse(out)) : [];
}

// Serves files with single and multiple byte ranges, as the differential download asks for them.
function serve(files, counted) {
  let bytes = 0;
  const server = http.createServer((request, response) => {
    const body = files[request.url.split('?')[0]];
    if (body === undefined) return (response.statusCode = 404), response.end();
    const ranges = /^bytes=(.+)$/.exec(request.headers.range || '')?.[1].split(',').map((part) => {
      const [start, end] = part.trim().split('-').map(Number);
      return [start, Number.isNaN(end) ? body.length - 1 : end];
    });
    const send = (chunk) => {
      if (request.url.endsWith(counted)) bytes += chunk.length;
      return chunk;
    };
    if (!ranges) return response.end(send(body));
    response.statusCode = 206;
    if (ranges.length === 1) {
      const [start, end] = ranges[0];
      response.setHeader('Content-Range', `bytes ${start}-${end}/${body.length}`);
      return response.end(send(body.subarray(start, end + 1)));
    }
    const boundary = 'va-boundary';
    response.setHeader('Content-Type', `multipart/byteranges; boundary=${boundary}`);
    const parts = ranges.map(([start, end]) => Buffer.concat([
      Buffer.from(`--${boundary}\r\nContent-Type: application/octet-stream\r\nContent-Range: bytes ${start}-${end}/${body.length}\r\n\r\n`),
      send(body.subarray(start, end + 1)),
      Buffer.from('\r\n'),
    ]));
    response.end(Buffer.concat([...parts, Buffer.from(`--${boundary}--\r\n`)]));
  });
  return { server, bytes: () => bytes };
}

test('an update installs silently and the app starts again', { skip: !INSTALLED && 'set VA_E2E_INSTALLED', timeout: 600_000 }, async (t) => {
  const { privateKey, publicKey } = crypto.generateKeyPairSync('ed25519');
  const info = yaml.load(fs.readFileSync(path.join(DIST, 'latest.yml'), 'utf8'));
  const current = info.version;
  const name = info.path;
  const installer = fs.readFileSync(path.join(DIST, name));
  const blockmap = fs.readFileSync(path.join(DIST, `${name}.blockmap`));
  const text = yaml.dump({ ...info, version: NEW, releaseNotes: '安装测试' }, { lineWidth: -1 });
  const sig = signature.sign(text, privateKey.export({ type: 'pkcs8', format: 'pem' }));
  const files = {
    '/releases/latest/download/latest.yml': text,
    '/releases/latest/download/latest.yml.sig': sig,
    [`/releases/download/v${NEW}/latest.yml`]: text,
    [`/releases/download/v${NEW}/latest.yml.sig`]: sig,
    [`/releases/download/v${NEW}/${name}`]: installer,
    [`/releases/download/v${NEW}/${name}.blockmap`]: blockmap,
    [`/releases/download/v${current}/${name}.blockmap`]: blockmap,
  };
  const { server, bytes } = serve(files, name);
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  // A failure must not leave the server listening, which keeps Node and the CI step running until GitHub's limit.
  t.after(() => (server.closeAllConnections(), server.close()));
  const userData = fs.mkdtempSync(path.join(os.tmpdir(), 'va-update-install-'));
  fs.writeFileSync(path.join(userData, 'settings.json'), JSON.stringify({ workspace: path.join(userData, 'workspace'), videos: [] }));
  const cacheCopy = path.join(process.env.LOCALAPPDATA, 'video-agent-gui-updater', 'installer.exe');
  assert.ok(fs.existsSync(cacheCopy), 'the installer keeps a copy of itself for differential downloads');

  const app = await electron.launch({
    executablePath: INSTALLED,
    args: [`--user-data=${userData}`],
    env: {
      ...process.env,
      VA_UPDATE_ROOT: `http://127.0.0.1:${server.address().port}/releases`,
      VA_UPDATE_PUBLIC_KEY: publicKey.export({ type: 'spki', format: 'der' }).toString('base64'),
      VA_UPDATE_DELAY_MS: '300',
      NO_PROXY: '127.0.0.1,localhost',
    },
  });
  const oldPid = app.process().pid;
  const page = await app.firstWindow();
  await page.click('#open-settings');
  await page.waitForFunction(() => /有新版本 9\.9\.9/.test(document.querySelector('#update-status').textContent), null, { timeout: 60_000 });
  await page.click('#update-download');
  await page.waitForFunction(() => /已下载并通过校验/.test(document.querySelector('#update-status').textContent), null, { timeout: 300_000 });
  const fetched = bytes();
  assert.ok(fetched < installer.length / 10, `differential download fetched ${fetched} of ${installer.length} bytes`);

  const closed = new Promise((resolve) => app.process().once('exit', resolve));
  await page.click('#update-install');
  await closed;

  let started = [];
  for (let i = 0; i < 180 && !started.length; i++) {
    await new Promise((resolve) => setTimeout(resolve, 1000));
    started = mainProcesses().filter((item) => item.ProcessId !== oldPid &&
      path.resolve(item.ExecutablePath || '').toLowerCase() === path.resolve(INSTALLED).toLowerCase());
  }
  // taskkill fails on children that are already exiting ("operation not supported"); only the main process matters.
  for (const item of started) spawnSync('taskkill.exe', ['/PID', String(item.ProcessId), '/T', '/F'], { windowsHide: true });
  assert.ok(started.length, 'the installer started the app again');

  const log = fs.readFileSync(path.join(userData, 'logs', 'main.log'), 'utf8');
  assert.match(log, /installing update 9\.9\.9/);
  const cli = path.join(path.dirname(INSTALLED), 'resources', 'cli').toLowerCase();
  const userPath = execFileSync('powershell.exe', ['-NoProfile', '-Command',
    "(Get-Item HKCU:\\Environment).GetValue('Path', '', 'DoNotExpandEnvironmentNames')"], { encoding: 'utf8' });
  assert.equal(userPath.trim().toLowerCase().split(';').filter((entry) => entry.replace(/\\$/, '') === cli).length, 1,
    'the update leaves exactly one PATH entry for the bundled CLI');
});
