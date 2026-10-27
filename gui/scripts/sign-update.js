// Release step: put the release notes into dist/latest.yml and sign it, writing dist/latest.yml.sig.
// Usage: node scripts/sign-update.js <dist folder> <release notes .md>, with the PKCS#8 PEM private key in
// UPDATE_SIGNING_KEY (a repository secret). Refuses a key that does not match the public key built into the app.

const fs = require('node:fs');
const path = require('node:path');
const yaml = require('js-yaml');
const signature = require('../src/update-signature');

const [dist, notesFile] = process.argv.slice(2);
const key = process.env.UPDATE_SIGNING_KEY;
if (!dist || !notesFile || !key) {
  console.error('usage: UPDATE_SIGNING_KEY=<pem> node scripts/sign-update.js <dist folder> <release notes .md>');
  process.exit(2);
}

const file = path.join(dist, 'latest.yml');
const info = yaml.load(fs.readFileSync(file, 'utf8'));
const version = require('../package.json').version;
if (info.version !== version) throw new Error(`latest.yml is for ${info.version}, package.json says ${version}`);
info.releaseNotes = fs.readFileSync(notesFile, 'utf8').trim();
const text = yaml.dump(info, { lineWidth: -1 });
const sig = signature.sign(text, key);
// VA_UPDATE_PUBLIC_KEY: the tests sign with a key of their own.
if (!signature.verify(text, sig, process.env.VA_UPDATE_PUBLIC_KEY || signature.PUBLIC_KEY)) {
  throw new Error('UPDATE_SIGNING_KEY does not match the public key in src/update-signature.js');
}
fs.writeFileSync(file, text);
fs.writeFileSync(`${file}.sig`, sig + '\n');
console.log(`signed ${file} for ${info.version} (${info.files.map((item) => item.url).join(', ')})`);
