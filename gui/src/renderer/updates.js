// Checking for and installing updates, and the release notes.

import { $, markdown, state } from './state.js';

export const SOURCE_PAGE = 'https://github.com/edsfod/video-agent';
const RELEASES_PAGE = `${SOURCE_PAGE}/releases`;
const megabytes = (bytes) => (bytes / 1048576).toFixed(1);

// 1, 0 or -1 as version a is newer than, the same as or older than b (plain x.y.z numbers).
// Semantic versions: 0.9.2-beta < 0.9.2-beta.2 < 0.9.2 (a pre-release comes before its full release).
function newer(a, b) {
  const parse = (version) => {
    const [core, pre] = version.split(/-(.*)/s);
    return [core.split('.').map(Number), pre ? pre.split('.') : null];
  };
  const [[x, xp], [y, yp]] = [parse(a), parse(b)];
  for (let i = 0; i < 3; i++) if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) > (y[i] || 0) ? 1 : -1;
  if (!xp || !yp) return xp === yp ? 0 : xp ? -1 : 1;
  for (let i = 0; i < Math.max(xp.length, yp.length); i++) {
    if (xp[i] === yp[i]) continue;
    if (xp[i] === undefined || yp[i] === undefined) return xp[i] === undefined ? -1 : 1;
    const [m, n] = [Number(xp[i]), Number(yp[i])];
    if (!Number.isNaN(m) && !Number.isNaN(n)) return m > n ? 1 : -1;
    return xp[i] > yp[i] ? 1 : -1;
  }
  return 0;
}

// 今天 14:33, 昨天 09:05, or 10月27日 14:33.
export function when(iso) {
  const date = new Date(iso);
  const time = date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  const days = Math.round((new Date().setHours(0, 0, 0, 0) - new Date(iso).setHours(0, 0, 0, 0)) / 86400000);
  return days === 0 ? `今天 ${time}` : days === 1 ? `昨天 ${time}` : `${date.getMonth() + 1}月${date.getDate()}日 ${time}`;
}

export function renderUpdate(update) {
  const current = update.current;
  state.appVersion = current;
  const last = update.lastCheck;
  // What that check found, against the version running now (it may have been installed since).
  const order = last ? newer(last.version, current) : 0;
  const found = order > 0 ? `，当时发现新版本 ${last.version}` : order === 0 ? '，没有更新的版本' : '';
  const lastText = last ? `上次检查更新：${when(last.at)}（经 ${last.source}）${found}。` : '还没有检查过更新。';
  const text = {
    idle: update.message ? `当前版本 ${current}。${update.message}` : `当前版本 ${current}。${lastText}`,
    checking: '正在检查更新…',
    latest: `当前版本 ${current}。${lastText}`,
    available: `有新版本 ${update.version}，当前是 ${current}。`,
    downloading: `正在经 ${update.source} 下载 ${update.version}：${Math.floor(update.percent || 0)}%` +
      (update.total ? `（${megabytes(update.transferred)} / ${megabytes(update.total)} MB）` : ''),
    downloaded: `${update.version} 已下载并通过校验，点“重启并安装”完成更新；设置和工作区都会保留。`,
    error: '检查更新没有成功，可以稍后再试，或打开发布页手动下载。',
  }[update.status];
  const failure = update.status !== 'idle' && update.message ? `\n${update.message}` : '';
  $('update-status').textContent = text + failure;
  $('update-check').disabled = ['checking', 'downloading', 'downloaded'].includes(update.status);
  $('update-download').hidden = update.status !== 'available';
  $('update-install').hidden = update.status !== 'downloaded';
  $('update-progress').hidden = update.status !== 'downloading';
  $('update-progress').value = update.percent || 0;
  const notes = ['available', 'downloading', 'downloaded'].includes(update.status) && update.notes;
  $('update-notes').hidden = !notes;
  if (notes) $('update-notes').innerHTML = markdown(notes);
  for (const link of $('update-notes').querySelectorAll('a[href]')) {
    link.onclick = (event) => (event.preventDefault(), window.va.external(link.href));
  }
  $('open-settings').classList.toggle('has-update', ['available', 'downloading', 'downloaded'].includes(update.status));
  $('open-settings').title = $('open-settings').classList.contains('has-update') ? `有新版本 ${update.version}` : '';
}

window.va.onUpdateState(renderUpdate);
$('update-check').onclick = () => window.va.checkUpdate();
$('update-download').onclick = () => window.va.downloadUpdate();
$('update-releases').onclick = () => window.va.external(RELEASES_PAGE);
$('update-install').onclick = async () => {
  const result = await window.va.installUpdate(false);
  if (result.running && confirm(`还有 ${result.running} 个任务在运行，安装更新会停止它们。现在安装吗？`)) {
    await window.va.installUpdate(true);
  }
};
