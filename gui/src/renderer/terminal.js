// The 终端 tab: an embedded shell (xterm.js in the page, node-pty in the main process).

import { $, current, element, state } from './state.js';

let ptyCounter = 0;

export function renderTerminal(video) {
  const select = $('shell-choice');
  if (!select.options.length) {
    for (const item of state.env.shells) select.append(element('option', { value: item.id, textContent: item.label }));
    select.value = state.settings.shell || state.env.shells[0]?.id || '';
  }
  // A shell starts only when asked for (user request, 2026-10-29), not on opening the tab.
  $('new-terminal').textContent = state.term ? '新建终端' : '启动终端';
  if (!state.term) {
    $('terminal').replaceChildren(element('p', { className: 'terminal-note', textContent: '点「启动终端」，在这个视频的处理结果文件夹里打开一个终端。' }));
  } else requestAnimationFrame(() => state.term?.fit.fit());
}

async function newTerminal(video) {
  if (state.term) {
    window.va.ptyKill(state.term.id);
    state.term.xterm.dispose();
  }
  const xterm = new Terminal({
    fontFamily: "'Cascadia Mono', Consolas, monospace",
    fontSize: 13,
    cursorBlink: true,
    theme: { background: '#1b1a18', foreground: '#ecebe6' },
  });
  const fit = new FitAddon.FitAddon();
  xterm.loadAddon(fit);
  $('terminal').replaceChildren();
  xterm.open($('terminal'));
  $('new-terminal').textContent = '新建终端';
  fit.fit();
  const id = `pty-${++ptyCounter}`;
  state.term = { id, xterm, fit };
  xterm.onData((data) => window.va.ptyWrite(id, data));
  xterm.onResize(({ cols, rows }) => window.va.ptyResize(id, cols, rows));
  const shellId = $('shell-choice').value;
  state.settings = await window.va.saveSettings({ shell: shellId });
  const cwd = video?.info?.processed ? video.info.folder : state.settings.workspace;
  await window.va.ptyStart({ id, shellId, cwd, cols: xterm.cols, rows: xterm.rows });
  xterm.focus();
}

window.va.onPtyData(({ id, data }) => state.term?.id === id && state.term.xterm.write(data));
window.va.onPtyExit(({ id }) => state.term?.id === id && state.term.xterm.write('\r\n[已退出，点「新建终端」重新打开]\r\n'));
$('new-terminal').onclick = () => newTerminal(current());
// Another shell replaces a running one; with none running, the choice waits for 启动终端.
$('shell-choice').onchange = () => state.term && newTerminal(current());
new ResizeObserver(() => state.term && state.tab === 'terminal' && state.term.fit.fit()).observe($('terminal'));
