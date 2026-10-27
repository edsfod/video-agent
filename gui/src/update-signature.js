// The release workflow signs latest.yml with an Ed25519 key kept in the repository's secrets and uploads the
// signature as latest.yml.sig (base64). The app trusts latest.yml only when it verifies against this public key, so a
// mirror that serves a different installer is refused: latest.yml carries the installer's sha512.

const crypto = require('node:crypto');

const PUBLIC_KEY = 'MCowBQYDK2VwAyEATWEwxhuVY6GVEjv7bA1qVHwtQt0M+dhxXPGYuYK+FvY=';

function verify(text, signature, publicKey = PUBLIC_KEY) {
  if (!signature) return false;
  const key = crypto.createPublicKey({ key: Buffer.from(publicKey, 'base64'), format: 'der', type: 'spki' });
  try {
    return crypto.verify(null, Buffer.from(text, 'utf8'), key, Buffer.from(String(signature).trim(), 'base64'));
  } catch {
    return false;
  }
}

function sign(text, privateKeyPem) {
  return crypto.sign(null, Buffer.from(text, 'utf8'), crypto.createPrivateKey(privateKeyPem)).toString('base64');
}

module.exports = { PUBLIC_KEY, verify, sign };
