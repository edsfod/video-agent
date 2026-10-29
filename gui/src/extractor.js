// AutoSlides Extractor, downloaded on the user's request into the app's data folder (user decision, 2026-10-29): the
// portable Windows build from its author's GitHub releases, so the installer stays as it is and the author's
// releases stay the source of its files. Where it is, every CLI this app starts finds it (childEnv sets
// AUTOSLIDES_EXTRACTOR), and process uses it for the screen pages.

const { app, net } = require('electron');
const { execFile } = require('node:child_process');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

const REPO = 'bit-admin/AutoSlides-Extractor';
// Tests point this at a local server: a release's JSON, as the GitHub API gives it.
const release = () => process.env.VA_EXTRACTOR_RELEASE || `https://api.github.com/repos/${REPO}/releases/latest`;
const ASSET = /Windows-x64-Portable\.zip$/;
const PROGRAM = 'AutoSlidesExtractor.exe';
// The same mirrors as for updates (updater.js); the file is checked against the release's digest either way.
const MIRRORS = ['https://gh-proxy.com/', 'https://ghfast.top/'];

const folder = () => path.join(app.getPath('userData'), 'tools', 'AutoSlides Extractor');

/** The downloaded AutoSlidesExtractor.exe, or null. */
function downloaded() {
  const search = (dir, depth) => {
    if (!fs.existsSync(dir)) return null;
    const direct = path.join(dir, PROGRAM);
    if (fs.existsSync(direct)) return direct;
    if (!depth) return null;
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const found = entry.isDirectory() && search(path.join(dir, entry.name), depth - 1);
      if (found) return found;
    }
    return null;
  };
  return search(folder(), 3);
}

/** @param {string} url @returns {Promise<any>} */
async function json(url) {
  const response = await net.fetch(url, { headers: { Accept: 'application/vnd.github+json' } });
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
  return response.json();
}

/**
 * Writes `url` to `file`, reporting progress; resolves to the file's SHA-256.
 * @param {string} url @param {string} file @param {(received: number) => void} progress
 */
async function save(url, file, progress) {
  const response = await net.fetch(url);
  if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`);
  const hash = crypto.createHash('sha256');
  const out = fs.createWriteStream(file);
  let received = 0;
  const reader = response.body.getReader();
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      hash.update(value);
      received += value.length;
      if (!out.write(value)) await new Promise((resolve) => out.once('drain', () => resolve(null)));
      progress(received);
    }
  } finally {
    await new Promise((resolve) => out.end(() => resolve(null)));
  }
  return hash.digest('hex');
}

/**
 * Downloads the latest portable build and unpacks it into the data folder, replacing an earlier one.
 * @param {(state: { source: string, received: number, total: number }) => void} onProgress
 * @returns {Promise<{ path: string, version: string }>}
 */
async function download(onProgress) {
  const latest = await json(release());
  const asset = (latest.assets || []).find((item) => ASSET.test(item.name));
  if (!asset) throw new Error(`${latest.tag_name} 没有 Windows 免安装版`);
  const digest = (asset.digest || '').replace(/^sha256:/, '');
  const work = fs.mkdtempSync(path.join(app.getPath('temp'), 'video-agent-extractor-'));
  try {
    const zip = path.join(work, asset.name);
    const urls = [asset.browser_download_url, ...MIRRORS.map((prefix) => prefix + asset.browser_download_url)];
    let failures = [];
    for (const url of urls) {
      const source = new URL(url).host;
      try {
        const sum = await save(url, zip, (received) => onProgress({ source, received, total: asset.size }));
        if (fs.statSync(zip).size !== asset.size) throw new Error('大小不对');
        if (digest && sum !== digest) throw new Error('校验不符');
        failures = [];
        break;
      } catch (error) {
        failures.push(`${source}：${error.message}`);
      }
    }
    if (failures.length) throw new Error(`下载失败（${failures.join('；')}）`);
    // Windows' own tar (bsdtar, since Windows 10 1803) unpacks zip files; a tar found first on PATH, such as Git's GNU
    // tar, does not.
    const unpacked = path.join(work, 'unpacked');
    fs.mkdirSync(unpacked);
    await new Promise((resolve, reject) =>
      execFile(path.join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'tar.exe'), ['-xf', zip, '-C', unpacked], { windowsHide: true }, (error) => (error ? reject(error) : resolve(null))),
    );
    fs.rmSync(folder(), { recursive: true, force: true });
    fs.cpSync(unpacked, folder(), { recursive: true }); // the temporary folder may be on another drive
    const program = downloaded();
    if (!program) throw new Error(`解压后找不到 ${PROGRAM}`);
    return { path: program, version: latest.tag_name };
  } finally {
    fs.rmSync(work, { recursive: true, force: true });
  }
}

module.exports = { download, downloaded };
