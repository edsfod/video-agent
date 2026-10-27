// installer/user-path.ps1 against a scratch registry key (HKCU\Software\VideoAgentTest-*), never the real PATH; no window.

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { execFileSync, spawnSync } = require('node:child_process');

const SCRIPT = path.join(__dirname, '..', 'installer', 'user-path.ps1');
const KEY = `Software\\VideoAgentTest-${process.pid}`;
const FOLDER = 'C:\\Program Files\\Video Agent\\resources\\cli';

const ps = (command) => execFileSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', command], { encoding: 'utf8' }).trim();
const run = (action, folder = FOLDER) =>
  execFileSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', SCRIPT, action, folder, '-Key', KEY]);
const read = () => ps(`$k = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('${KEY}'); if ($k -and ($k.GetValueNames() -contains 'Path')) { $k.GetValueKind('Path').ToString() + '|' + $k.GetValue('Path', '', 'DoNotExpandEnvironmentNames') } else { '<none>' }`);
const write = (value, kind = 'ExpandString') =>
  ps(`$k = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey('${KEY}'); $k.SetValue('Path', '${value}', [Microsoft.Win32.RegistryValueKind]::${kind})`);

test.after(() => spawnSync('reg.exe', ['delete', `HKCU\\${KEY}`, '/f']));

for (const [name, value, kind] of [
  ['a trailing semicolon', 'C:\\a;%USERPROFILE%\\bin;', 'ExpandString'],
  ['no trailing semicolon', 'C:\\a;%USERPROFILE%\\bin', 'ExpandString'],
  ['empty entries in the middle', 'C:\\a;;C:\\b', 'String'],
]) {
  test(`add then remove gives back the same PATH: ${name}`, () => {
    write(value, kind);
    run('add');
    const added = read();
    assert.equal(added.split('|')[0], kind, 'the value type stays');
    assert.ok(added.toLowerCase().includes(FOLDER.toLowerCase()), added);
    assert.ok(added.includes('%USERPROFILE%') || !value.includes('%'), 'variables stay unexpanded');
    run('add');
    assert.equal(read(), added, 'adding twice changes nothing');
    run('remove');
    assert.equal(read(), `${kind}|${value}`);
  });
}

test('remove matches case-insensitively and with a trailing backslash', () => {
  write(`C:\\a;${FOLDER.toUpperCase()}\\;C:\\b`);
  run('remove');
  assert.equal(read(), 'ExpandString|C:\\a;C:\\b');
});

test('a PATH that did not exist is created and removed again', () => {
  spawnSync('reg.exe', ['delete', `HKCU\\${KEY}`, '/f']);
  run('add');
  assert.equal(read(), `ExpandString|${FOLDER}`);
  run('remove');
  assert.equal(read(), '<none>');
});
