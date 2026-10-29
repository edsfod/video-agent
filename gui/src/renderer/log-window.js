// The 日志 window.

import { $, baseName, element } from './state.js';
import { addLocalVideos } from './video-list.js';

$('open-logs').onclick = async () => {
  const entries = await window.va.logs();
  const list = $('log-list');
  list.replaceChildren(
    ...entries.map((entry) => {
      const failed = entry.exit !== null && entry.exit !== 0;
      const status = entry.exit === null ? '未结束或被中断' : entry.exit === 0 ? `完成 · ${entry.seconds} 秒` : `退出码 ${entry.exit}`;
      const item = element('div', { className: 'log-entry' }, [
        element('div', { textContent: entry.title || baseName(entry.file) }),
        element('div', {
          className: 'meta' + (failed ? ' fail' : ''),
          textContent: `${new Date(entry.started).toLocaleString('zh-CN')} · ${status}`,
        }),
      ]);
      item.onclick = async () => {
        for (const other of list.children) other.classList.remove('active');
        item.classList.add('active');
        // The first and last lines are metadata for the list; show the command instead.
        const body = (await window.va.readLog(entry.file)).split('\n').filter((line) => !line.startsWith('# {')).join('\n');
        $('log-view').textContent = `$ ${(entry.command || []).join(' ')}\n\n${body.trim()}\n`;
      };
      return item;
    }),
  );
  $('log-view').textContent = entries.length ? '选择左边的一条记录查看完整输出。' : '还没有任务记录。';
  $('logs').showModal();
  list.firstElementChild?.click();
};
$('close-logs').onclick = () => $('logs').close();
$('open-log-folder').onclick = () => window.va.openLogs();

window.addEventListener('error', (event) => window.va.logError(event.error?.stack || event.message));
window.addEventListener('unhandledrejection', (event) => window.va.logError(event.reason?.stack || event.reason));
window.va.onTrayAddVideos(async () => addLocalVideos(await window.va.pickVideos()));
