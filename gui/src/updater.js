// Checks GitHub Releases for a newer desktop app and installs it when the user asks; nothing is downloaded on its own.
// electron-updater does the download, the sha512 check, the differential download against the installer copy kept in
// %LOCALAPPDATA%\video-agent-gui-updater, and the silent reinstall. This file adds three sources tried in turn
// (github.com, the GitHub API, mirrors) and the signature check on latest.yml (update-signature.js), which is what
// makes an untrusted mirror safe to use.

const { app } = require('electron');
const { autoUpdater } = require('electron-updater');
const { GenericProvider } = require('electron-updater/out/providers/GenericProvider');
const { Provider, parseUpdateInfo, resolveFiles } = require('electron-updater/out/providers/Provider');
const { CancellationToken } = require('builder-util-runtime');
const signature = require('./update-signature');
const updatePlan = require('./update-plan');

const REPO = 'edsfod/video-agent';
const RELEASES = `https://github.com/${REPO}/releases`;
// Third-party GitHub download proxies, used only after github.com and the API fail. They are not trusted: whatever
// they serve must match the signed latest.yml. A mirror set in the settings comes first; gh-proxy.com was the faster
// of the two on a direct connection (2026-10-27: about 2.5 MB/s against 0.4 MB/s, one measurement).
const MIRRORS = ['https://gh-proxy.com/', 'https://ghfast.top/'];
const REQUEST_TIMEOUT = 15_000; // per metadata request; Electron's requests never time out on their own
const STALL_TIMEOUT = 60_000; // a download with no progress for this long is cancelled and the next source tried
// A download that is moving but slowly also moves on, to the next source that downloads only the changed blocks
// (user request, 2026-10-29: 0.9.0 came from github.com at about 0.4 MB/s, where gh-proxy.com had given 2.5 MB/s).
// After SLOW.after ms, a source averaging under SLOW.speed bytes/s with more than SLOW.left s still to go at that
// speed is left. The last such source is kept however slow, and a slow source left behind is tried once more, without
// this check, when every later one failed. Tests: VA_UPDATE_SLOW=<after ms>,<bytes/s>,<seconds left>.
const [slowAfter, slowSpeed, slowLeft] = (process.env.VA_UPDATE_SLOW || '15000,300000,60').split(',').map(Number);
const SLOW = { after: slowAfter, speed: slowSpeed, left: slowLeft };

const publicKey = () => process.env.VA_UPDATE_PUBLIC_KEY || signature.PUBLIC_KEY; // a test key for the e2e tests

// Metadata requests with a timeout. electron-updater reuses a check that is still running, so a slow source has to
// fail by itself before the next one can be asked.
async function request(provider, url, headers) {
  const token = new CancellationToken();
  const timer = setTimeout(() => token.cancel(), REQUEST_TIMEOUT);
  try {
    return await Provider.prototype.httpRequest.call(provider, url, headers, token);
  } catch (error) {
    if (token.cancelled) throw new Error(`连接 ${url.host} 超时`);
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

async function signedInfo(provider, ymlUrl, sigUrl, headers) {
  const [text, sig] = await Promise.all([request(provider, ymlUrl, headers), request(provider, sigUrl, headers)]);
  if (!signature.verify(text, sig, publicKey())) throw new Error(`${ymlUrl.host} 给出的 latest.yml 没有通过签名校验`);
  return parseUpdateInfo(text, 'latest.yml', ymlUrl);
}

// github.com or a mirror in front of it: `url` is a releases root, such as https://github.com/<repo>/releases.
class ReleaseProvider extends GenericProvider {
  // One byte range per request. github.com and ghfast.top answer a request for several ranges with 501, and
  // electron-updater then downloads the whole installer instead of the changed blocks (0.4.0 and 0.5.0 fetched about
  // 157 MB where 9 MB had changed); its own GitHub provider turns this off for the same reason.
  constructor(configuration, updater, runtimeOptions) {
    super(configuration, updater, { ...runtimeOptions, isUseMultipleRangeRequest: false });
  }

  async getLatestVersion() {
    const root = this.configuration.url.replace(/\/+$/, '');
    const latest = `${root}/latest/download/`;
    const info = await signedInfo(this, new URL('latest.yml', latest), new URL('latest.yml.sig', latest));
    // Download from the versioned folder: electron-updater finds the old blockmap by putting the old version wherever
    // the new one appears in the path, so the folder must carry the version as well as the file name does.
    this.baseUrl = new URL(`${root}/download/v${info.version}/`);
    return info;
  }
}

// The REST API (api.github.com, assets from release-assets.githubusercontent.com), for networks where github.com
// itself hangs but these answer.
class ApiProvider extends Provider {
  constructor(configuration, updater, runtimeOptions) {
    super({ ...runtimeOptions, isUseMultipleRangeRequest: false });
    this.configuration = configuration;
    this.updater = updater;
    this.assets = new Map();
  }

  get fileExtraDownloadHeaders() {
    return { Accept: 'application/octet-stream' };
  }

  async getLatestVersion() {
    const url = new URL(`https://api.github.com/repos/${REPO}/releases/latest`);
    const release = JSON.parse(await request(this, url, { Accept: 'application/vnd.github+json' }));
    this.assets = new Map((release.assets || []).map((asset) => [asset.name, asset.url]));
    const asset = (name) => {
      if (!this.assets.has(name)) throw new Error(`发布 ${release.tag_name} 里没有 ${name}`);
      return new URL(this.assets.get(name));
    };
    return signedInfo(this, asset('latest.yml'), asset('latest.yml.sig'), { Accept: 'application/octet-stream' });
  }

  resolveFiles(info) {
    return resolveFiles(info, new URL('https://api.github.com/'), (name) => this.assets.get(name) ?? name);
  }
}

function sources(mirror) {
  // Tests: VA_UPDATE_ROOT=<releases root>[,<another>…], tried in order like the real sources.
  if (process.env.VA_UPDATE_ROOT) {
    return process.env.VA_UPDATE_ROOT.split(',').map((url, i) => ({ name: `测试源 ${i + 1}`, provider: ReleaseProvider, url }));
  }
  const prefixes = [mirror, ...MIRRORS].map((item) => (item || '').trim()).filter(Boolean).map((item) => item.replace(/\/*$/, '/'));
  return [
    { name: 'GitHub', provider: ReleaseProvider, url: RELEASES },
    // Asset URLs carry no version, so electron-updater cannot find the old blockmap: always a full download.
    { name: 'GitHub API', provider: ApiProvider, url: '', differential: false },
    ...[...new Set(prefixes)].map((prefix) => ({
      name: `镜像 ${new URL(prefix).host}`,
      provider: ReleaseProvider,
      url: prefix + RELEASES,
    })),
  ];
}

function notesText(notes) {
  if (Array.isArray(notes)) return notes.map((item) => item.note).filter(Boolean).join('\n\n');
  return notes || '';
}

function reason(error) {
  return String(error?.message || error).split('\n')[0].slice(0, 200);
}

// settings(): the current settings; remember(changes): saves them; send(channel, value): to the window; running():
// number of running jobs.
function createUpdater({ logs, send, settings, remember, running }) {
  updatePlan.install();
  autoUpdater.autoDownload = false;
  autoUpdater.autoInstallOnAppQuit = false;
  autoUpdater.forceDevUpdateConfig = !!process.env.VA_UPDATE_ROOT; // the e2e tests also run the unpackaged app
  autoUpdater.logger = {
    info: (message) => logs.line('info', `updater: ${message}`),
    warn: (message) => logs.line('warn', `updater: ${message}`),
    error: (message) => logs.line('error', `updater: ${message}`),
    debug: () => {},
  };
  // electron-updater uses its own session, which follows the system proxy but not these variables.
  const proxy = process.env.HTTPS_PROXY || process.env.https_proxy || process.env.HTTP_PROXY || process.env.http_proxy;
  if (proxy) autoUpdater.netSession.setProxy({ proxyRules: proxy }).catch(() => {});

  // The last check that got an answer, kept across restarts so the window can say when it was rather than only
  // "up to date" (user request, 2026-10-28).
  let state = { status: 'idle', current: app.getVersion(), lastCheck: settings().lastUpdateCheck || null };
  let index = 0; // the source that answered the last check
  let token = null;
  let stall = null;
  let attempt = null; // the running download: { started, slow (whether it may be left for being slow), why }
  const set = (changes) => {
    state = { ...state, ...changes };
    send('update:state', state);
    return state;
  };
  const watch = () => {
    clearTimeout(stall);
    stall = setTimeout(() => token?.cancel(), STALL_TIMEOUT);
  };
  // Before any progress the size is not known yet, so the time left counts as long.
  const tooSlow = () => {
    if (!attempt?.slow || !token || Date.now() - attempt.started < SLOW.after) return;
    const speed = (state.transferred || 0) / ((Date.now() - attempt.started) / 1000);
    const left = state.total ? (state.total - state.transferred) / Math.max(speed, 1) : Infinity;
    if (speed >= SLOW.speed || left <= SLOW.left) return;
    attempt.why = `太慢（约 ${Math.round(speed / 1000)} KB/s）`;
    token.cancel();
  };

  autoUpdater.on('error', () => {}); // failures are logged per source below; an unhandled 'error' event would throw
  autoUpdater.on('download-progress', (progress) => {
    watch();
    set({ percent: progress.percent, transferred: progress.transferred, total: progress.total, speed: progress.bytesPerSecond });
    tooSlow();
  });

  function use(i) {
    const source = sources(settings().updateMirror)[i];
    autoUpdater.disableDifferentialDownload = source.differential === false;
    autoUpdater.setFeedURL({ provider: 'custom', updateProvider: source.provider, url: source.url });
    return source;
  }

  async function check() {
    if (['checking', 'downloading', 'downloaded'].includes(state.status)) return state;
    set({ status: 'checking', message: '' });
    const failures = [];
    const count = sources(settings().updateMirror).length;
    for (let i = 0; i < count; i++) {
      const source = use(i);
      try {
        const result = await autoUpdater.checkForUpdates();
        if (!result) return set({ status: 'idle', message: '开发版不检查更新。' });
        index = i;
        const info = result.updateInfo;
        logs.line('info', `update check via ${source.name}: latest ${info.version}, running ${app.getVersion()}`);
        const lastCheck = { at: new Date().toISOString(), version: info.version, source: source.name };
        remember({ lastUpdateCheck: lastCheck });
        return set({
          status: result.isUpdateAvailable ? 'available' : 'latest',
          version: info.version,
          notes: notesText(info.releaseNotes),
          source: source.name,
          lastCheck,
        });
      } catch (error) {
        failures.push(`${source.name}：${reason(error)}`);
        logs.line('warn', `update check via ${source.name} failed: ${reason(error)}`);
      }
    }
    return set({ status: 'error', message: failures.join('\n') });
  }

  async function download() {
    if (state.status !== 'available') return state;
    const failures = [];
    const all = sources(settings().updateMirror);
    // A source that downloads the whole installer (the API) is no way out of a slow one that downloads only the
    // changed blocks.
    const order = [...all.keys()].slice(index);
    const left = new Set(); // sources left for being slow
    while (order.length) {
      const i = order.shift();
      if (left.size && !left.has(i) && all[i].differential === false) continue;
      const source = use(i);
      const later = order.some((j) => !left.has(j) && all[j].differential !== false);
      set({ status: 'downloading', percent: 0, transferred: 0, total: 0, source: source.name, message: failures.join('\n') });
      try {
        // Checking again binds the download to this source and refreshes its signed latest.yml.
        const result = await autoUpdater.checkForUpdates();
        if (!result?.isUpdateAvailable) throw new Error(`${source.name} 上没有比 ${app.getVersion()} 新的版本`);
        token = new CancellationToken();
        attempt = { started: Date.now(), slow: later && !left.has(i) };
        watch();
        const check = setInterval(tooSlow, 1000); // also when no progress comes at all
        try {
          await autoUpdater.downloadUpdate(token);
        } finally {
          clearInterval(check);
        }
        clearTimeout(stall);
        index = i;
        logs.line('info', `update ${result.updateInfo.version} downloaded via ${source.name}`);
        return set({ status: 'downloaded', version: result.updateInfo.version, percent: 100, message: '' });
      } catch (error) {
        clearTimeout(stall);
        const message = attempt?.why || (token?.cancelled ? `${STALL_TIMEOUT / 1000} 秒没有进度` : reason(error));
        failures.push(`${source.name}：${message}${attempt?.why ? '，换下一个' : ''}`);
        logs.line('warn', `update download via ${source.name} failed: ${message}`);
        if (attempt?.why) {
          left.add(i);
          order.push(i); // once more at the end, without the speed check
        }
      } finally {
        token = null;
        attempt = null;
      }
    }
    return set({ status: 'available', message: `下载没有成功：\n${failures.join('\n')}` });
  }

  // Quits, runs the installer silently and starts the new version. Running jobs would be stopped, so the window asks
  // first unless force is set.
  function install(force) {
    if (state.status !== 'downloaded') return { ok: false };
    if (!force && running() > 0) return { ok: false, running: running() };
    logs.line('info', `installing update ${state.version}`);
    setImmediate(() => autoUpdater.quitAndInstall(true, true));
    return { ok: true };
  }

  return { check, download, install, state: () => state };
}

module.exports = { createUpdater, sources, ReleaseProvider, ApiProvider };
