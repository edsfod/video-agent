// Site accounts for downloads (user request, 2026-10-29: not only Bilibili, in an order of one's own, hiding the ones
// not used). yt-dlp cannot read the cookies of a running Edge or Chrome (locked database, app-bound encryption since
// Chromium 127), so each site is opened once in a window of our own; its cookies live in a persistent partition of its
// own (encrypted with DPAPI in the packaged app, see `electronFuses` in package.json) and are exported to a Netscape
// cookies file only for the length of a download from that site.
//
// What each site needs, from yt-dlp's source (2026.10.26): Bilibili lists subtitles, AI ones included, only to a
// logged-in account; Douyin refuses without fresh cookies, "not necessarily logged in", which visiting the site sets
// (`s_v_web_id`); YouTube needs them for age-restricted and members-only videos and when it asks to "confirm you're not
// a bot". Google may refuse to sign in inside an embedded browser, so a cookies.txt exported from a browser can be
// imported instead, for any site.

const { BrowserWindow, session, shell } = require('electron');
const fs = require('node:fs');
const path = require('node:path');

// `ready`: the cookie without which there is nothing to give yt-dlp; `account`: the one a login sets (the login window
// closes by itself once it appears); `cookies`: the domains whose cookies yt-dlp gets; `urls`: links from this site.
const SITES = {
  bilibili: {
    name: '哔哩哔哩',
    why: 'B 站只给登录的账号看字幕（包括 AI 字幕）。登录后下载 B 站视频会把字幕一起存下来，处理时直接用，不用转录。',
    loginUrl: 'https://passport.bilibili.com/login',
    ready: 'SESSDATA',
    account: 'SESSDATA',
    cookies: /(^|\.)bilibili\.com$/,
    urls: /(^|[/.])(bilibili\.com|b23\.tv)([/:?#]|$)/i,
  },
  douyin: {
    name: '抖音',
    why: '不先打开一次抖音网页，yt-dlp 下载抖音视频会被拒绝；打开就行，不一定要登录，网页加载完关掉窗口即可。',
    loginUrl: 'https://www.douyin.com/',
    ready: 's_v_web_id',
    account: 'sessionid',
    cookies: /(^|\.)douyin\.com$/,
    urls: /(^|[/.])(douyin\.com|iesdouyin\.com)([/:?#]|$)/i,
  },
  youtube: {
    name: 'YouTube',
    why: '一般的视频和字幕不用登录；年龄限制、会员视频，以及 YouTube 要求“登录以确认你不是机器人”时才需要。Google 可能不让在这里登录，那就从浏览器导出 cookies.txt 再导入。',
    loginUrl: 'https://accounts.google.com/ServiceLogin?service=youtube&continue=https%3A%2F%2Fwww.youtube.com%2F',
    ready: 'SAPISID',
    account: 'SAPISID',
    cookies: /(^|\.)youtube\.com$/,
    urls: /(^|[/.])(youtube\.com|youtu\.be)([/:?#]|$)/i,
  },
};
const NAV_URL = 'https://api.bilibili.com/x/web-interface/nav';

// Bilibili keeps its old partition name, so a login from before stays.
const store = (key) => session.fromPartition(`persist:${key}`);

// Sites refuse or degrade for an "Electron/…" user agent; send the plain Chrome one.
function plainAgent(key) {
  return store(key).getUserAgent().replace(/ (Electron|video-agent-gui)\/\S+/g, '');
}

function siteOf(url) {
  return Object.keys(SITES).find((key) => SITES[key].urls.test(url || '')) || null;
}

async function cookie(key, name) {
  const site = SITES[key];
  const found = (await store(key).cookies.get({ name })).find((item) => site.cookies.test(item.domain.replace(/^\./, '')));
  return found && (!found.expirationDate || found.expirationDate * 1000 > Date.now()) ? found : null;
}

// { key, name, why, ready, loggedIn, user? }. Bilibili's account name comes from its own endpoint; without network the
// login still counts.
async function status(key) {
  const site = SITES[key];
  const base = { key, name: site.name, why: site.why, urls: site.urls.source }; // the window tells links apart too
  const ready = !!(await cookie(key, site.ready));
  const loggedIn = !!(await cookie(key, site.account));
  if (key !== 'bilibili' || !loggedIn) return { ...base, ready, loggedIn };
  try {
    const response = await store(key).fetch(NAV_URL, { headers: { 'User-Agent': plainAgent(key) } });
    const body = await response.json();
    if (body.code === -101) return { ...base, ready: false, loggedIn: false }; // the server no longer accepts the cookie
    return { ...base, ready, loggedIn, user: body.data?.uname };
  } catch {
    return { ...base, ready, loggedIn };
  }
}

const list = () => Promise.all(Object.keys(SITES).map(status));

// Opens the site's login page and resolves with `status()` once the login cookie appears or the window is closed.
function login(key, parent) {
  const site = SITES[key];
  return new Promise((resolve) => {
    const window = new BrowserWindow({
      parent,
      modal: true,
      width: 960,
      height: 720,
      title: `登录${site.name}`,
      autoHideMenuBar: true,
      webPreferences: { partition: `persist:${key}`, contextIsolation: true, sandbox: true },
    });
    window.webContents.setUserAgent(plainAgent(key));
    window.webContents.setWindowOpenHandler(({ url }) => {
      if (/^https?:\/\//.test(url)) shell.openExternal(url); // agreements and help pages
      return { action: 'deny' };
    });
    let timer;
    const changed = (_, item, __, removed) => {
      // Give the page a moment to set the rest of its cookies after the login one.
      if (item.name === site.account && !removed && site.cookies.test(item.domain.replace(/^\./, ''))) {
        timer ??= setTimeout(() => window.isDestroyed() || window.close(), 1500);
      }
    };
    store(key).cookies.on('changed', changed);
    window.on('closed', async () => {
      clearTimeout(timer);
      store(key).cookies.removeListener('changed', changed);
      resolve(await status(key));
    });
    window.loadURL(site.loginUrl);
  });
}

async function logout(key) {
  await store(key).clearStorageData();
  return status(key);
}

// Reads a Netscape cookies file (as browser extensions and `yt-dlp --cookies-from-browser … --cookies` write it) and
// keeps the site's cookies from it. Returns { count, status }.
async function importCookies(key, file) {
  const site = SITES[key];
  let count = 0;
  for (const line of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
    const httpOnly = line.startsWith('#HttpOnly_');
    if (!line.trim() || (line.startsWith('#') && !httpOnly)) continue;
    const fields = (httpOnly ? line.slice('#HttpOnly_'.length) : line).split('\t');
    if (fields.length < 7) continue;
    const [domain, subdomains, cookiePath, secure, expires, name, ...value] = fields;
    const host = domain.replace(/^\./, '');
    if (!site.cookies.test(host)) continue;
    const details = {
      url: `${secure === 'TRUE' ? 'https' : 'http'}://${host}${cookiePath || '/'}`,
      name,
      value: value.join('\t'),
      path: cookiePath || '/',
      secure: secure === 'TRUE',
      httpOnly,
      ...(subdomains === 'TRUE' ? { domain: `.${host}` } : {}),
      ...(Number(expires) > 0 ? { expirationDate: Number(expires) } : {}),
    };
    await store(key).cookies.set(details);
    count++;
  }
  return { count, status: await status(key) };
}

// Writes the partition's cookies for the site to `file` in the Netscape format yt-dlp reads; returns null when there
// is nothing to give.
async function writeCookies(key, file) {
  const site = SITES[key];
  if (!(await cookie(key, site.ready))) return null;
  const cookies = (await store(key).cookies.get({})).filter((item) => site.cookies.test(item.domain.replace(/^\./, '')));
  const lines = cookies.map((item) => {
    const domain = item.hostOnly || item.domain.startsWith('.') ? item.domain : `.${item.domain}`;
    return [
      (item.httpOnly ? '#HttpOnly_' : '') + domain,
      item.hostOnly ? 'FALSE' : 'TRUE',
      item.path || '/',
      item.secure ? 'TRUE' : 'FALSE',
      Math.floor(item.expirationDate || 0),
      item.name,
      item.value,
    ].join('\t');
  });
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, `# Netscape HTTP Cookie File\n${lines.join('\n')}\n`, { mode: 0o600 });
  return file;
}

module.exports = { SITES, siteOf, status, list, login, logout, importCookies, writeCookies };
