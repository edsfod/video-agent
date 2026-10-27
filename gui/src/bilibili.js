// Bilibili login for subtitle downloads. Bilibili lists subtitles, AI ones included, only to a logged-in account, and
// yt-dlp cannot read the cookies of a running Edge or Chrome (locked database, app-bound encryption since Chromium
// 127). So the user logs in once in a window of our own; its cookies live in a separate persistent partition (encrypted
// with DPAPI in the packaged app, see `electronFuses` in package.json) and are exported to a Netscape cookies file only
// for the length of a download.

const { BrowserWindow, session, shell } = require('electron');
const fs = require('node:fs');
const path = require('node:path');

const PARTITION = 'persist:bilibili';
const LOGIN_URL = 'https://passport.bilibili.com/login';
const NAV_URL = 'https://api.bilibili.com/x/web-interface/nav';

const store = () => session.fromPartition(PARTITION);

// Bilibili's pages refuse or degrade for an "Electron/…" user agent; send the plain Chrome one.
function plainAgent() {
  return store().getUserAgent().replace(/ (Electron|video-agent-gui)\/\S+/g, '');
}

async function loginCookie() {
  const [cookie] = await store().cookies.get({ domain: 'bilibili.com', name: 'SESSDATA' });
  return cookie && (!cookie.expirationDate || cookie.expirationDate * 1000 > Date.now()) ? cookie : null;
}

// { loggedIn, name? }. The name comes from Bilibili's own account endpoint; without network the login still counts.
async function status() {
  if (!(await loginCookie())) return { loggedIn: false };
  try {
    const response = await store().fetch(NAV_URL, { headers: { 'User-Agent': plainAgent() } });
    const body = await response.json();
    if (body.code === -101) return { loggedIn: false }; // the server no longer accepts the cookie
    return { loggedIn: true, name: body.data?.uname };
  } catch {
    return { loggedIn: true };
  }
}

// Opens the login page and resolves with `status()` once the login cookie appears or the window is closed.
function login(parent) {
  return new Promise((resolve) => {
    const window = new BrowserWindow({
      parent,
      modal: true,
      width: 960,
      height: 720,
      title: '登录哔哩哔哩',
      autoHideMenuBar: true,
      webPreferences: { partition: PARTITION, contextIsolation: true, sandbox: true },
    });
    window.webContents.setUserAgent(plainAgent());
    window.webContents.setWindowOpenHandler(({ url }) => {
      if (/^https?:\/\//.test(url)) shell.openExternal(url); // agreements and help pages
      return { action: 'deny' };
    });
    let timer;
    const changed = (_, cookie, __, removed) => {
      // Give the page a moment to set the rest of its cookies after SESSDATA.
      if (cookie.name === 'SESSDATA' && !removed) timer ??= setTimeout(() => window.isDestroyed() || window.close(), 1500);
    };
    store().cookies.on('changed', changed);
    window.on('closed', async () => {
      clearTimeout(timer);
      store().cookies.removeListener('changed', changed);
      resolve(await status());
    });
    window.loadURL(LOGIN_URL);
  });
}

async function logout() {
  await store().clearStorageData();
  return { loggedIn: false };
}

// Writes the partition's Bilibili cookies to `file` in the Netscape format yt-dlp reads; returns null when logged out.
async function writeCookies(file) {
  if (!(await loginCookie())) return null;
  const cookies = (await store().cookies.get({})).filter((cookie) => /(^|\.)bilibili\.com$/.test(cookie.domain));
  const lines = cookies.map((cookie) => {
    const domain = cookie.hostOnly || cookie.domain.startsWith('.') ? cookie.domain : `.${cookie.domain}`;
    return [
      (cookie.httpOnly ? '#HttpOnly_' : '') + domain,
      cookie.hostOnly ? 'FALSE' : 'TRUE',
      cookie.path || '/',
      cookie.secure ? 'TRUE' : 'FALSE',
      Math.floor(cookie.expirationDate || 0),
      cookie.name,
      cookie.value,
    ].join('\t');
  });
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, `# Netscape HTTP Cookie File\n${lines.join('\n')}\n`, { mode: 0o600 });
  return file;
}

module.exports = { status, login, logout, writeCookies, PARTITION };
