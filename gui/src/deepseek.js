// DeepSeek's web chat (chat.deepseek.com) in a window of its own, used as a person would use it: the user signs in
// there, and ask() attaches the files, types the text, sends it and reads the answer (user decision, 2026-10-29: the
// official page, not a reverse-engineered API). Nothing here knows about videos, so it serves any round of text and
// files; another chat site would be a module with the same ask().
//
// What the page offers, as found on 2026-10-29: a textarea; toggle buttons (.ds-toggle-button, selected with
// --selected) for DeepThink and Search; a hidden input[type=file] that takes many files; a round send button
// (.ds-button--primary.ds-button--circle), disabled while uploads run or the box is empty, whose icon turns into a
// stop square while an answer is written; each answer, and the thinking before it, in a .ds-markdown block, where a
// code block is a <pre> whose text is the Markdown as written.

const { BrowserWindow } = require('electron');

const URL = process.env.VA_DEEPSEEK_URL || 'https://chat.deepseek.com/';
const PARTITION = 'persist:deepseek';
// Test windows stay off the screen and never take the focus (as window.js does for the main window).
const BACKGROUND = !!process.env.VA_E2E_BACKGROUND;
const ANSWER_TIMEOUT_MS = 30 * 60 * 1000; // a long DeepThink answer took about 3 minutes; this only ends a hung page

/** @type {BrowserWindow | null} */
let win = null;
let stopped = false;

const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function open() {
  if (win && !win.isDestroyed()) {
    if (!BACKGROUND) win.show();
    return win;
  }
  win = new BrowserWindow({
    width: 1100,
    height: 860,
    title: 'DeepSeek',
    show: !BACKGROUND,
    ...(BACKGROUND ? { x: -32000, y: -32000, skipTaskbar: true } : {}),
    webPreferences: { partition: PARTITION, contextIsolation: true, sandbox: true },
  });
  win.removeMenu();
  if (BACKGROUND) win.showInactive();
  win.on('closed', () => (win = null));
  win.loadURL(URL);
  return win;
}

/** @param {string} code */
const page = (code) => {
  if (!win || win.isDestroyed()) throw new Error('DeepSeek 窗口已关闭');
  return win.webContents.executeJavaScript(code);
};

// The composer: the textarea's box with the attachments, the toggles and the send button.
const COMPOSER = `(() => { let box = document.querySelector('textarea'); for (let i = 0; i < 6 && box?.parentElement; i++) box = box.parentElement; return box; })()`;
const SEND = `[...(${COMPOSER})?.querySelectorAll('.ds-button--primary.ds-button--circle') || []].pop()`;

async function waitFor(check, what, onStatus, timeout = Infinity) {
  const start = Date.now();
  let told = false;
  for (;;) {
    if (stopped) throw new Error('已停止');
    if (await page(check).catch(() => false)) return;
    if (Date.now() - start > timeout) throw new Error(`等不到${what}`);
    if (!told && Date.now() - start > 5000) {
      onStatus(`等待${what}…`);
      told = true;
    }
    await pause(1000);
  }
}

/** @param {BrowserWindow} view @param {string[]} files */
async function attach(view, files) {
  const debug = view.webContents.debugger;
  if (!debug.isAttached()) debug.attach('1.3');
  const { root } = await debug.sendCommand('DOM.getDocument', { depth: -1, pierce: true });
  const { nodeId } = await debug.sendCommand('DOM.querySelector', { nodeId: root.nodeId, selector: 'input[type=file]' });
  if (!nodeId) throw new Error('DeepSeek 页面上找不到上传文件的地方');
  await debug.sendCommand('DOM.setFileInputFiles', { nodeId, files });
}

/**
 * Sends `text` with `files` and returns the answer: the text of its longest code block (the Markdown as written), or
 * the answer's text when it has none (`fenced` false).
 * @param {{ text: string, files?: string[], newChat?: boolean, onStatus?: (line: string) => void }} message
 * @returns {Promise<{ answer: string, fenced: boolean }>}
 */
async function ask({ text, files = [], newChat = false, onStatus = () => {} }) {
  stopped = false;
  const view = open();
  if (newChat) await view.loadURL(URL);
  await waitFor("!!document.querySelector('textarea')", '登录 DeepSeek（在 DeepSeek 窗口里登录）', onStatus);
  // DeepThink and Search on (user decision, 2026-10-29): search serves the 补充 a summary may add.
  await page(`(() => { for (const b of document.querySelectorAll('.ds-toggle-button')) if (!b.classList.contains('ds-toggle-button--selected')) b.click(); })()`);
  const answersBefore = await page(`document.querySelectorAll('.ds-markdown').length`);
  if (files.length) await attach(view, files);
  await page(`document.querySelector('textarea').focus()`);
  view.webContents.insertText(text);
  await waitFor(`(() => { const b = ${SEND}; return !!b && !b.classList.contains('ds-button--disabled'); })()`, '图片上传完', onStatus, 10 * 60 * 1000);
  const idle = await page(`${SEND}.querySelector('svg path')?.getAttribute('d') || ''`);
  await page(`${SEND}.click()`);
  onStatus('已发送，DeepSeek 正在写…');
  // Written once the button has shown something else (the stop square) and is back to its idle icon.
  const start = Date.now();
  let writing = false;
  for (;;) {
    if (stopped) throw new Error('已停止');
    if (Date.now() - start > ANSWER_TIMEOUT_MS) throw new Error('DeepSeek 半小时没有写完');
    await pause(2000);
    const icon = await page(`${SEND}?.querySelector('svg path')?.getAttribute('d') || ''`);
    if (icon !== idle) writing = true;
    else if (writing || Date.now() - start > 60000) {
      const count = await page(`document.querySelectorAll('.ds-markdown').length`);
      if (count > answersBefore) break;
    }
  }
  const read = await page(`(() => {
    const blocks = [...document.querySelectorAll('.ds-markdown')];
    const last = blocks[blocks.length - 1];
    const code = [...last.querySelectorAll('pre')].map((pre) => pre.textContent).sort((a, b) => b.length - a.length)[0];
    return { code: code || null, text: last.innerText };
  })()`);
  onStatus(`DeepSeek 写完了，用时 ${Math.round((Date.now() - start) / 1000)} 秒`);
  return read.code ? { answer: read.code, fenced: true } : { answer: read.text, fenced: false };
}

function stop() {
  stopped = true;
}

module.exports = { ask, open, stop };
