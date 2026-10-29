// Site accounts (accounts.js: which sites need one, and why), the link box and downloads.

import { $, $$, current, element, pageVideo, state } from './state.js';
import { addTask } from './task-panel.js';
import { addLocalVideos, persistList, renderList } from './video-list.js';
import { renderVideo } from './video-view.js';

// Links whose download fails or misses subtitles without the site's cookies, and what the hint under the link says.
const ACCOUNT_HINTS = {
  bilibili: ['没有登录 B 站，只能下载视频，拿不到字幕。', '登录'],
  douyin: ['还没在这里打开过抖音网页，下载抖音视频会被拒绝。', '打开'],
};
const accountOf = (url) => state.accounts.find((account) => new RegExp(account.urls, 'i').test(url || ''));

// The settings' order first, then any site added since; hidden ones apart.
function accountOrder() {
  const keys = state.accounts.map((account) => account.key);
  const order = (state.settings.accountOrder || []).filter((key) => keys.includes(key));
  return [...order, ...keys.filter((key) => !order.includes(key))];
}

async function saveAccountLayout(changes) {
  state.settings = await window.va.saveSettings(changes);
  renderAccounts();
}

/** @param {{ loggedIn: boolean, ready: boolean, user?: string }} account */
function accountState({ loggedIn, ready, user }) {
  if (loggedIn) return `已登录${user ? `：${user}` : ''}`;
  return ready ? '可以下载（没有登录）' : '没有登录';
}

async function accountAction(key, action) {
  const status = await action(key);
  state.accounts = state.accounts.map((account) => (account.key === key ? status : account));
  renderAccounts();
}

export function renderAccounts() {
  const hidden = state.settings.hiddenAccounts || [];
  const order = accountOrder();
  const shown = order.filter((key) => !hidden.includes(key));
  const move = (key, by) => {
    const next = [...order];
    const from = next.indexOf(key);
    next.splice(from, 1);
    next.splice(Math.max(0, Math.min(next.length, from + by)), 0, key);
    saveAccountLayout({ accountOrder: next });
  };
  $('accounts').replaceChildren(
    ...shown.map((key, i) => {
      const account = /** @type {Awaited<ReturnType<import('../va').Va['accounts']>>[number]} */ (state.accounts.find((item) => item.key === key)); // shown lists known sites
      const button = (text, onclick, extra = {}) => Object.assign(element('button', { type: 'button', textContent: text, ...extra }), { onclick });
      const row = element('div', { className: 'account' }, [
        element('div', { className: 'account-text' }, [
          element('span', { className: 'account-name', textContent: account.name }),
          element('span', { className: 'muted small-text account-state', textContent: accountState(account) }),
          element('p', { className: 'muted small-text', textContent: account.why }),
        ]),
        element('span', { className: 'row account-buttons' }, [
          button(account.loggedIn ? '重新登录' : key === 'douyin' && !account.ready ? '打开' : '登录', () => accountAction(key, window.va.accountLogin)),
          button('从浏览器导入…', () => openCookieDialog(key), { className: 'ghost', title: '读取浏览器里的登录状态，或导入扩展导出的 cookies.txt' }),
          ...(account.ready || account.loggedIn ? [button('退出登录', () => accountAction(key, window.va.accountLogout), { className: 'ghost' })] : []),
          button('↑', () => move(key, -1), { className: 'ghost small', title: '往前', disabled: i === 0 }),
          button('↓', () => move(key, 1), { className: 'ghost small', title: '往后', disabled: i === shown.length - 1 }),
          button('隐藏', () => saveAccountLayout({ hiddenAccounts: [...hidden, key] }), { className: 'ghost small' }),
        ]),
      ]);
      row.dataset.account = key;
      return row;
    }),
  );
  $('accounts-hidden').hidden = !hidden.length;
  $('accounts-hidden').replaceChildren(
    '已隐藏：',
    ...order.filter((key) => hidden.includes(key)).flatMap((key, i) => {
      const link = element('a', { href: '#', textContent: state.accounts.find((item) => item.key === key)?.name || key });
      link.title = '显示';
      link.onclick = (event) => (event.preventDefault(), saveAccountLayout({ hiddenAccounts: hidden.filter((item) => item !== key) }));
      return i ? ['、', link] : [link];
    }),
  );
  renderDownloadHint();
}

// One site's import: from a browser yt-dlp can read, or from a cookies.txt an extension exported (user request,
// 2026-10-29: show how, or read a chosen browser in one click).
let cookieSite = null;
async function openCookieDialog(key) {
  cookieSite = key;
  const account = state.accounts.find((item) => item.key === key);
  if (!account) return;
  $('cookie-title').textContent = `导入${account.name}的登录状态`;
  for (const span of $$('#cookie-dialog .cookie-site')) span.textContent = account.name;
  $('cookie-home').textContent = account.home;
  $('cookie-home').href = account.home;
  $('cookie-state').hidden = true;
  const browsers = await window.va.browsers();
  $('cookie-browsers').replaceChildren(
    ...(browsers.length
      ? browsers.map((browser) => {
          const pick = element('button', { type: 'button', textContent: `从 ${browser.name} 读取` });
          pick.onclick = () => cookieImport(window.va.accountFromBrowser(key, browser.key), `正在读取 ${browser.name}…`);
          return pick;
        })
      : [element('span', { className: 'muted small-text', textContent: '没有找到 Firefox、Edge、Chrome 或 Brave。' })]),
  );
  $('cookie-dialog').showModal();
}

async function cookieImport(pending, waiting) {
  const line = $('cookie-state');
  line.hidden = false;
  line.className = 'small-text';
  line.textContent = waiting || '';
  const result = await pending;
  if (!result) return (line.hidden = true); // the file dialog was cancelled
  if (result.error) {
    line.className = 'small-text warn';
    line.textContent = result.error;
    return;
  }
  state.accounts = state.accounts.map((account) => (account.key === cookieSite ? result.status : account));
  renderAccounts();
  const name = result.status.name;
  if (!result.count) line.textContent = `没有找到${name}的 Cookie：先在那个浏览器里打开${name}并登录，再试一次。`;
  else if (!result.status.ready && cookieSite !== 'douyin') line.textContent = `导入了 ${result.count} 条${name}的 Cookie，但里面没有登录状态：那个浏览器没有登录${name}。先在浏览器里登录，再试一次。`;
  else line.textContent = `导入了 ${result.count} 条${name}的 Cookie，现在${accountState(result.status)}。`;
}

$('cookie-file').onclick = () => cookieImport(window.va.accountImport(cookieSite));
for (const link of $$('#cookie-dialog a')) {
  link.onclick = (event) => (event.preventDefault(), /^https?:/.test(link.href) && window.va.external(link.href));
}

function renderDownloadHint() {
  const account = accountOf($('download-url').value.trim());
  const hint = account && !account.ready && ACCOUNT_HINTS[account.key];
  $('download-hint').hidden = !hint;
  if (!hint) return;
  $('download-hint-text').textContent = hint[0];
  $('download-login').textContent = hint[1];
}

$('download-login').onclick = (event) => {
  event.preventDefault();
  const account = accountOf($('download-url').value.trim());
  if (account) accountAction(account.key, window.va.accountLogin);
};
$('download-url').oninput = renderDownloadHint;

$('download-form').onsubmit = (event) => {
  event.preventDefault();
  const url = $('download-url').value.trim();
  if (!url) return;
  const then = $('download-then-process').checked ? 'process' : undefined;
  addTask({ kind: 'download', title: `下载：${url}`, url, then });
};
// A link that stands for a list (a season, a series, a channel) is not downloaded until the user says so.
let pendingList = null;
export function askPlaylist(found, then) {
  pendingList = { url: found.url, then };
  const title = found.title || found.url;
  $('playlist-dialog-info').textContent = `这个链接是一个列表：「${title}」，共 ${found.count} 个视频。`;
  const shown = found.titles.filter(Boolean);
  $('playlist-dialog-titles').replaceChildren(
    ...shown.map((name) => element('li', { textContent: name })),
    ...(found.count > shown.length && shown.length ? [element('li', { textContent: '…' })] : []),
  );
  $('playlist-dialog-titles').hidden = !shown.length;
  $('playlist-dialog-name').value = title.replace(/^合集[·・:：]\s*/, '');
  $('playlist-dialog-join').checked = true;
  $('playlist-dialog-follow').checked = true;
  $('playlist-dialog-auto').checked = false;
  renderPlaylistDialog();
  $('playlist-dialog').showModal();
}
// Following needs a collection to keep the list in; checking on its own needs following.
function renderPlaylistDialog() {
  const joined = $('playlist-dialog-join').checked;
  $('playlist-dialog-name-label').hidden = !joined;
  $('playlist-dialog-follow-label').hidden = !joined;
  $('playlist-dialog-auto-label').hidden = !joined || !$('playlist-dialog-follow').checked;
}
$('playlist-dialog-join').onchange = renderPlaylistDialog;
$('playlist-dialog-follow').onchange = renderPlaylistDialog;
$('playlist-dialog').addEventListener('close', async () => {
  if ($('playlist-dialog').returnValue !== 'save' || !pendingList) return;
  const { url, then } = pendingList;
  pendingList = null;
  const collection = $('playlist-dialog-join').checked ? $('playlist-dialog-name').value.trim() : '';
  const follow = Boolean(collection) && $('playlist-dialog-follow').checked;
  const auto = follow && $('playlist-dialog-auto').checked;
  const added = await addTask({
    kind: 'download', title: `下载列表：${collection || url}`, url, then, playlist: true,
    collection: collection || undefined, follow, auto,
  });
  if (added && $('download-url').value.trim() === url) $('download-url').value = '';
});

$('download-then-process').onchange = () =>
  window.va.saveSettings({ processAfterDownload: $('download-then-process').checked }).then((next) => (state.settings = next));

$('reveal-video').onclick = () => window.va.reveal(pageVideo().path);
$('reveal-folder').onclick = () => {
  const info = pageVideo().info;
  if (info?.processed) window.va.open(info.folder);
};
$('remove-video').onclick = async () => {
  state.videos = state.videos.filter((video) => video.path !== state.current);
  state.current = state.videos[0]?.path || null;
  await persistList();
  renderList();
  renderVideo();
};

document.addEventListener('dragover', (event) => event.preventDefault());
document.addEventListener('drop', (event) => {
  event.preventDefault();
  const paths = [...(event.dataTransfer?.files || [])].map((file) => window.va.droppedPath(file)).filter(Boolean);
  if (paths.length) addLocalVideos(paths);
});
