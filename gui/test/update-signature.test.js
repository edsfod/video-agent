// The signature on latest.yml and the release script that writes it; no window.

const test = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync, spawnSync } = require('node:child_process');
const signature = require('../src/update-signature');

function keyPair() {
  const { privateKey, publicKey } = crypto.generateKeyPairSync('ed25519');
  return {
    pem: privateKey.export({ type: 'pkcs8', format: 'pem' }),
    pub: publicKey.export({ type: 'spki', format: 'der' }).toString('base64'),
  };
}

test('a signature verifies only for the same text and key', () => {
  const { pem, pub } = keyPair();
  const text = 'version: 9.9.9\nreleaseNotes: 中文说明\n';
  const sig = signature.sign(text, pem);
  assert.ok(signature.verify(text, sig, pub));
  assert.ok(signature.verify(text, `${sig}\n`, pub), 'a trailing newline in the .sig file is fine');
  assert.ok(!signature.verify(text.replace('9.9.9', '9.9.8'), sig, pub));
  assert.ok(!signature.verify(text, sig, keyPair().pub));
  assert.ok(!signature.verify(text, '', pub));
  assert.ok(!signature.verify(text, 'not base64 at all', pub));
});

test('the built-in public key is a valid Ed25519 key', () => {
  const key = crypto.createPublicKey({ key: Buffer.from(signature.PUBLIC_KEY, 'base64'), format: 'der', type: 'spki' });
  assert.equal(key.asymmetricKeyType, 'ed25519');
});

test('sign-update adds the notes, signs latest.yml and refuses a key the app would not accept', () => {
  const { pem, pub } = keyPair();
  const dist = fs.mkdtempSync(path.join(os.tmpdir(), 'va-sign-'));
  const version = require('../package.json').version;
  fs.writeFileSync(path.join(dist, 'latest.yml'),
    `version: ${version}\nfiles:\n  - url: Video-Agent-Setup-${version}.exe\n    sha512: abc\n    size: 3\npath: Video-Agent-Setup-${version}.exe\nsha512: abc\n`);
  const notes = path.join(dist, 'notes.md');
  fs.writeFileSync(notes, '**新增**：测试\n');
  const script = path.join(__dirname, '..', 'scripts', 'sign-update.js');
  execFileSync(process.execPath, [script, dist, notes], { env: { ...process.env, UPDATE_SIGNING_KEY: pem, VA_UPDATE_PUBLIC_KEY: pub } });
  const text = fs.readFileSync(path.join(dist, 'latest.yml'), 'utf8');
  assert.match(text, /releaseNotes: '\*\*新增\*\*：测试'/);
  assert.ok(signature.verify(text, fs.readFileSync(path.join(dist, 'latest.yml.sig'), 'utf8'), pub));

  const refused = spawnSync(process.execPath, [script, dist, notes], { env: { ...process.env, UPDATE_SIGNING_KEY: pem, VA_UPDATE_PUBLIC_KEY: '' } });
  assert.notEqual(refused.status, 0);
  assert.match(String(refused.stderr), /does not match the public key/);
});
