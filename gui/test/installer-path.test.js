// The installer's PATH choice (CI only: set VA_E2E_SETUP to the built Video-Agent-Setup-*.exe). Silent installs use
// the remembered choice, on by default; the uninstaller removes the entry and the remembered choice.

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync, spawnSync } = require('node:child_process');

const SETUP = process.env.VA_E2E_SETUP;
const KEY = 'HKCU\\Software\\Video Agent';
// Progress on stdout, which the CI log shows as it comes, so a step that hangs is seen while it hangs.
const START = Date.now();
const step = (text) => console.log(`[installer-path ${((Date.now() - START) / 1000).toFixed(1)}s] ${text}`);

function run(file, args) {
  const result = spawnSync(file, args, { timeout: 300_000, windowsHide: true });
  assert.equal(result.status, 0, `${path.basename(file)} ${args.join(' ')} exited with ${result.status}`);
}

function userPath() {
  return execFileSync('powershell.exe', ['-NoProfile', '-Command',
    "(Get-Item HKCU:\\Environment).GetValue('Path', '', 'DoNotExpandEnvironmentNames')"], { encoding: 'utf8' }).trim();
}

const onPath = (dir) => userPath().toLowerCase().split(';').includes(path.join(dir, 'resources', 'cli').toLowerCase());
const choice = () => spawnSync('reg.exe', ['query', KEY, '/v', 'AddToPath'], { encoding: 'utf8' }).stdout.match(/0x([01])/)?.[1];

function installAndRemove(expectOnPath) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'va-path-'));
  const before = userPath();
  step(`installing silently, PATH ${expectOnPath ? 'expected' : 'not expected'}`);
  run(SETUP, ['/S', `/D=${dir}`]);
  assert.equal(onPath(dir), expectOnPath);
  assert.equal(choice(), expectOnPath ? '1' : '0');
  step('uninstalling');
  run(path.join(dir, 'Uninstall Video Agent.exe'), ['/S', `_?=${dir}`]);
  assert.equal(onPath(dir), false);
  assert.equal(choice(), undefined, 'the uninstaller forgets the choice');
  assert.equal(userPath(), before, 'PATH is back as it was');
}

test('PATH: added by default, left alone after opting out', { skip: !SETUP && 'set VA_E2E_SETUP', timeout: 900_000 }, () => {
  spawnSync('reg.exe', ['delete', KEY, '/f']);
  installAndRemove(true);
  execFileSync('reg.exe', ['add', KEY, '/v', 'AddToPath', '/t', 'REG_DWORD', '/d', '0', '/f']);
  installAndRemove(false);
});
