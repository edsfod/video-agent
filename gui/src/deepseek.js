// DeepSeek's web chat (chat.deepseek.com) in a window of its own, used as a person would use it: the user signs in
// there, and ask() attaches the files, types the text, sends it and reads the answer (user decision, 2026-10-29: the
// official page, not a reverse-engineered API). Nothing here knows about videos, so it serves any round of text and
// files; another chat site would be a module with the same ask().
//
// What the page offers, as found on 2026-10-29: a textarea; toggle buttons (.ds-toggle-button, selected with
// --selected) for DeepThink and Search; a hidden input[type=file] that takes many files; a round send button
// (.ds-button--primary.ds-button--circle), disabled while uploads run or the box is empty, whose icon turns into a
// stop square while an answer is written; each answer, and the thinking before it, in a .ds-markdown block, where a
// code block is a <pre> whose text is the Markdown as written; each attachment, a .ds-animated-size-item in the composer
// with the file's name as its picture's alt text and a line saying the upload failed when it did. A picture is a card
// ([role=button]) that, once failed, tries again when clicked, without the file being chosen anew: the page keeps it,
// and if it has reached the server asks only after it (user report, 2026-10-30; in the page's script as retryFile).
// Until the attached pictures are read, the answer's place says 正在分析图片 (Analyzing image) with no .ds-markdown yet.
// The page only draws while Chromium counts the window as seen, which main.js and backgroundThrottling see to.
//
// Some of what happens never shows on the page, so its requests are watched too (DevTools protocol, as attach() uses,
// reading only): POST /api/v0/chat/completion carries chat_session_id, parent_message_id, prompt and ref_file_ids, and
// answers with a stream of events; refused for sending too often, the stream is a `hint` event with finish_reason
// rate_limit_reached, shown for a moment if at all, and /api/v0/file/upload_file answers biz_msg "rate limit reached",
// which the attachment shows as Server busy (seen 2026-10-30).
//
// Each conversation has a window of its own (user request, 2026-10-30: DeepSeek summaries at the same time); they share
// the signed-in session, and a window whose conversation ended well serves the next one.

const { BrowserWindow } = require('electron');
const path = require('node:path');

const URL = process.env.VA_DEEPSEEK_URL || 'https://chat.deepseek.com/';
const PARTITION = 'persist:deepseek';
// Test windows stay off the screen and never take the focus (as window.js does for the main window).
const BACKGROUND = !!process.env.VA_E2E_BACKGROUND;
const ANSWER_TIMEOUT_MS = 30 * 60 * 1000; // a long DeepThink answer took about 3 minutes; this only ends a hung page

/** Windows of conversations that ended, signed in, for the next one. @type {BrowserWindow[]} */
const idle = [];
let signedIn = 0; // when a window last found the page signed in, for the windows still showing the sign-in page
// The limit on sending is the account's, not a conversation's (user report, 2026-10-30: read from the server, two
// conversations stopped within seconds of each other, at their 6th and 2nd message, and a new one could upload nothing),
// so the windows share these.
let nextSend = 0; // no window sends before this
let resumeAt = 0; // nor before this, after a refusal
let refusals = 0; // in a row, each waited on longer

const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function open() {
  const kept = idle.splice(0).filter((win) => !win.isDestroyed());
  const win =
    kept.shift() ||
    new BrowserWindow({
      width: 1100,
      height: 860,
      title: 'DeepSeek',
      show: !BACKGROUND,
      ...(BACKGROUND ? { x: -32000, y: -32000, skipTaskbar: true } : {}),
      webPreferences: { partition: PARTITION, contextIsolation: true, sandbox: true, backgroundThrottling: false },
    });
  idle.push(...kept);
  win.removeMenu();
  if (BACKGROUND) win.showInactive();
  else win.show();
  return win;
}

// The composer: the textarea's box with the attachments, the toggles and the send button.
const COMPOSER = `(() => { let box = document.querySelector('textarea'); for (let i = 0; i < 6 && box?.parentElement; i++) box = box.parentElement; return box; })()`;
const SEND = `[...(${COMPOSER})?.querySelectorAll('.ds-button--primary.ds-button--circle') || []].pop()`;

// DeepSeek's servers are sometimes busy (user report, 2026-10-29): an upload fails or never ends, or the answer is only
// a busy notice. A failed upload is tried again from its card (user report, 2026-10-30: all 49 again failed three times
// over), up to TRIES times, after which the whole message is tried again: it never goes without a file, as the import
// takes what was sent and not linked for pictures looked at and not needed. Still Server busy by then is waited out as a
// refusal is, for the same user report: it says nothing is wrong with the file. Uploads that never end,
// busy notices and answers that never start (user report, 2026-10-30: 正在分析图片 for 8 minutes, the message not on the
// server) are tried again whole, up to TRIES times, the page loaded again first, which keeps the conversation and
// empties the box.
//
// A refusal for sending too often is not such a failure: the task waits it out, however long, then goes on with the
// message it was on (user decision, 2026-10-30), and a gap between messages, across the windows, keeps it from coming.
// 21 messages in 15 minutes from four conversations at once were refused and still were 14 minutes later; 15 in 20
// minutes were not (2026-10-30). What the limit is, DeepSeek does not say.
const TRIES = 3;
const BUSY = /服务器繁忙|稍后再试|server is busy|try again later|并发请求过多|too many concurrent requests/i;
const UPLOAD_FAILED = /上传失败|重新上传|upload failed|failed to upload|服务器繁忙|server (?:is )?busy/i;
const UPLOAD_BUSY = /服务器繁忙|server (?:is )?busy/i;
const REFUSED = /"finish_reason":"rate_limit_reached"|"biz_msg":"rate limit reached"/;
const WATCHED = /\/api\/v\d+\/(?:chat\/completion|file\/upload_file)\b/;
const SENDING = /\/api\/v\d+\/chat\/completion\b/;
const READING_IMAGES = /正在分析图片|Analyzing image/i;
const UPLOAD_TIMEOUT_MS = 5 * 60 * 1000;
const BUSY_PAUSE_MS = Number(process.env.VA_DEEPSEEK_RETRY_MS) || 30000; // tests wait less
const UPLOAD_PAUSE_MS = BUSY_PAUSE_MS / 6;
const SEND_GAP_MS = Number(process.env.VA_DEEPSEEK_GAP_MS) || 60 * 1000; // Claude judgment, between the two rates above
const LIMIT_PAUSE_MS = Number(process.env.VA_DEEPSEEK_LIMIT_MS) || 5 * 60 * 1000; // doubled each time, up to the next
const LIMIT_PAUSE_MOST_MS = 6 * LIMIT_PAUSE_MS;
// Pictures were read and the thinking begun within seconds of sending, 49 pictures included; the one that hung did
// not start in 8 minutes.
const START_TIMEOUT_MS = Number(process.env.VA_DEEPSEEK_START_MS) || 3 * 60 * 1000; // tests wait less
const SETTLE_MS = 1500; // between two readings of a finished answer, which must be the same

const ATTACHMENTS = `[...(${COMPOSER})?.querySelectorAll('.ds-animated-size-item') || []]`;
const NAME = `(item) => item.querySelector('img')?.alt || item.innerText.split('\\n')[0]`;

/** A conversation in a window of its own: ask() for each message, stop() from outside, close() when it is over. */
function conversation() {
  const win = open();
  let stopped = false;
  // What the page's requests said about the message being sent.
  /** @type {{ refused: boolean, answering: boolean, sent: any }} */
  let wire = { refused: false, answering: false, sent: null };

  /** @param {string} code */
  const page = (code) => {
    if (win.isDestroyed()) throw new Error('DeepSeek 窗口已关闭');
    return win.webContents.executeJavaScript(code);
  };

  // Blocks of earlier answers the page draws after the marking before sending, as it does while a conversation loads,
  // must not pass for the new one (user report, 2026-10-30: an answer read in a round that never reached the server).
  const MARK = `document.querySelectorAll('.ds-markdown').forEach((block) => (block.dataset.vaSeen = ''))`;
  const requests = new Map();
  /** @param {any} _ @param {string} method @param {any} event */
  async function onRequest(_, method, event) {
    const debug = win.webContents.debugger;
    if (method === 'Network.requestWillBeSent' && event.request.method === 'POST' && WATCHED.test(event.request.url)) {
      const sending = SENDING.test(event.request.url);
      requests.set(event.requestId, sending);
      if (!sending) return;
      const body = event.request.postData || (await debug.sendCommand('Network.getRequestPostData', { requestId: event.requestId }).then((data) => data.postData, () => ''));
      try {
        wire.sent = JSON.parse(body);
      } catch {} // not read, so not checked
    } else if (method === 'Network.responseReceived' && requests.get(event.requestId)) {
      await page(MARK).catch(() => {});
      wire.answering = true;
    } else if (method === 'Network.loadingFinished' && requests.has(event.requestId)) {
      requests.delete(event.requestId);
      const { body } = await debug.sendCommand('Network.getResponseBody', { requestId: event.requestId }).catch(() => ({ body: '' }));
      if (REFUSED.test(body)) wire.refused = true;
    }
  }

  async function watch() {
    const debug = win.webContents.debugger;
    if (!debug.isAttached()) debug.attach('1.3');
    if (debug.listeners('message').includes(onRequest)) return;
    debug.on('message', onRequest);
    await debug.sendCommand('Network.enable');
  }

  // Waits for this window's turn to send: past a refusal and the gap after the last message of any window.
  async function turn(onStatus) {
    let told = false;
    for (;;) {
      if (stopped) throw new Error('已停止');
      const wait = Math.max(nextSend, resumeAt) - Date.now();
      if (wait <= 0) break;
      if (!told && wait > 5000) {
        onStatus(Date.now() < resumeAt ? `DeepSeek 限流中，约 ${Math.ceil(wait / 60000)} 分钟后再发` : `隔开发送，${Math.ceil(wait / 1000)} 秒后发`);
        told = true;
      }
      await pause(Math.min(wait, 1000));
    }
    nextSend = Date.now() + SEND_GAP_MS;
  }

  // Several windows are refused at about the same time; that is one refusal.
  function refused() {
    if (Date.now() < resumeAt) return;
    resumeAt = Date.now() + Math.min(LIMIT_PAUSE_MS * 2 ** refusals, LIMIT_PAUSE_MOST_MS);
    refusals += 1;
  }

  /** The reason, if what went out is not what was meant to. @param {string} text @param {string[]} files @param {boolean} newChat */
  function wrongMessage(text, files, newChat) {
    const { parent_message_id: parent, prompt, ref_file_ids: attached } = wire.sent || {};
    // User report, 2026-10-30: a new task's first message went into the conversation of the task that failed before it,
    // as one .txt file, with neither the prompt nor the pictures.
    if (newChat && parent != null) return '这条消息接到了别的对话后面';
    if (typeof prompt === 'string' && prompt.length < text.length / 2) return '提示词没有发全';
    if (Array.isArray(attached) && attached.length < files.length) return `只带上了 ${attached.length} 张图，应该是 ${files.length} 张`;
    return '';
  }

  // Waits until the page is signed in; a window still on the sign-in page loads again once another window is in.
  async function signIn(onStatus) {
    const start = Date.now();
    let seen = signedIn;
    let told = false;
    for (;;) {
      if (stopped) throw new Error('已停止');
      if (await page("!!document.querySelector('textarea')").catch(() => false)) break;
      if (signedIn > seen) {
        seen = signedIn;
        win.webContents.reload();
      }
      if (!told && Date.now() - start > 5000) {
        onStatus('等待登录 DeepSeek（在 DeepSeek 窗口里登录）…');
        told = true;
      }
      await pause(1000);
    }
    signedIn = Date.now();
  }

  /** @param {string[]} files */
  async function attach(files) {
    const debug = win.webContents.debugger;
    if (!debug.isAttached()) debug.attach('1.3');
    const { root } = await debug.sendCommand('DOM.getDocument', { depth: -1, pierce: true });
    const { nodeId } = await debug.sendCommand('DOM.querySelector', { nodeId: root.nodeId, selector: 'input[type=file]' });
    if (!nodeId) throw new Error('DeepSeek 页面上找不到上传文件的地方');
    await debug.sendCommand('DOM.setFileInputFiles', { nodeId, files });
  }

  /** The attachments whose upload failed. @returns {Promise<{ name: string, busy: boolean }[]>} */
  const failedUploads = () =>
    page(`${ATTACHMENTS}.filter((item) => ${UPLOAD_FAILED}.test(item.innerText)).map((item) => ({ name: (${NAME})(item), busy: ${UPLOAD_BUSY}.test(item.innerText) }))`);
  const retryUploads = () =>
    page(`${ATTACHMENTS}.filter((item) => ${UPLOAD_FAILED}.test(item.innerText)).forEach((item) => item.querySelector('[role=button]')?.click())`);

  /** Attaches the files and types the text; resolves once the send button may be pressed. */
  async function compose(text, files, onStatus) {
    if (files.length) await attach(files);
    await page(`document.querySelector('textarea').focus()`);
    win.webContents.insertText(text);
    const ready = `(() => { const b = ${SEND}; return !!b && !b.classList.contains('ds-button--disabled'); })()`;
    const tries = new Map(files.map((file) => [path.basename(file), 1]));
    const start = Date.now();
    let told = false;
    for (;;) {
      if (stopped) throw new Error('已停止');
      if (wire.refused) throw Object.assign(new Error('DeepSeek 限流'), { refused: true });
      const failed = await failedUploads();
      if (failed.length) {
        const lost = failed.filter(({ name }) => (tries.get(name) || TRIES) >= TRIES);
        if (lost.length && lost.every(({ busy }) => busy)) throw Object.assign(new Error('DeepSeek 上传繁忙'), { refused: true });
        if (lost.length) throw Object.assign(new Error(`${lost.map(({ name }) => name).join('、')} 上传 ${TRIES} 次都失败`), { again: true });
        const attempt = Math.max(...failed.map(({ name }) => tries.get(name))) + 1;
        onStatus(`${failed.length} 张图片上传失败，点重试（第 ${attempt} 次）`);
        for (const { name } of failed) tries.set(name, tries.get(name) + 1);
        await pause(UPLOAD_PAUSE_MS);
        await retryUploads();
        await pause(1000); // until the page has taken it, the send button still says what it said before
        continue;
      }
      if (await page(ready)) return;
      if (Date.now() - start > UPLOAD_TIMEOUT_MS) throw Object.assign(new Error('图片五分钟没有传完'), { again: true });
      if (!told && Date.now() - start > 5000) {
        onStatus('等待图片上传完…');
        told = true;
      }
      await pause(1000);
    }
  }

  /**
   * Presses send and waits until the answer is written; returns it.
   * @param {(line: string) => void} onStatus @param {() => string} wrong what is wrong with the message that went out
   */
  async function sendAndRead(onStatus, wrong) {
    // The answers on the page are marked, and the new one is the last block without the mark: the page does not keep
    // every earlier answer (user report, 2026-10-30: the first round's blocks were gone by the third, so counting them
    // missed the third answer).
    await page(MARK);
    const answered = `(() => { const blocks = document.querySelectorAll('.ds-markdown'); return !!blocks.length && !('vaSeen' in blocks[blocks.length - 1].dataset); })()`;
    const idleIcon = await page(`${SEND}.querySelector('svg path')?.getAttribute('d') || ''`);
    await page(`${SEND}.click()`);
    onStatus('已发送，DeepSeek 正在写…');
    // Written once the button has shown something else (the stop square) and is back to its idle icon.
    const start = Date.now();
    let writing = false;
    for (;;) {
      if (stopped) throw new Error('已停止');
      if (Date.now() - start > ANSWER_TIMEOUT_MS) throw new Error('DeepSeek 半小时没有写完');
      await pause(2000);
      if (wire.refused) throw Object.assign(new Error('DeepSeek 限流'), { refused: true });
      const problem = wrong();
      if (problem) throw Object.assign(new Error(problem), { again: true });
      const started = wire.answering && (await page(answered));
      if (started) refusals = 0;
      if (!started && Date.now() - start > START_TIMEOUT_MS) {
        const reading = READING_IMAGES.test(await page('document.body.innerText'));
        throw Object.assign(new Error(`发出 ${Math.round(START_TIMEOUT_MS / 1000)} 秒还没有开始写${reading ? '（一直显示「正在分析图片」）' : ''}`), { again: true });
      }
      const icon = await page(`${SEND}?.querySelector('svg path')?.getAttribute('d') || ''`);
      if (icon !== idleIcon) writing = true;
      else if ((writing || Date.now() - start > 60000) && started) break;
    }
    // The last lines reach the page a moment after the button is back (user report, 2026-10-30: the 画面 lines at the
    // end of four answers were missing as read, though DeepSeek had them), so the answer is read until it stays the
    // same.
    const answer = `(() => {
      const blocks = [...document.querySelectorAll('.ds-markdown')];
      const last = blocks[blocks.length - 1];
      const code = [...last.querySelectorAll('pre')].map((pre) => pre.textContent).sort((a, b) => b.length - a.length)[0];
      return { code: code || null, text: last.innerText };
    })()`;
    let read = await page(answer);
    for (let tries = 0; tries < 10; tries++) {
      await pause(SETTLE_MS);
      const again = await page(answer);
      if (again.text === read.text && again.code === read.code) break;
      read = again;
    }
    return { ...read, seconds: Math.round((Date.now() - start) / 1000) };
  }

  /**
   * Sends `text` with `files` and returns the answer: the text of its longest code block (the Markdown as written), or
   * the answer's text when it has none (`fenced` false).
   * @param {{ text: string, files?: string[], newChat?: boolean, onStatus?: (line: string) => void }} message
   * @returns {Promise<{ answer: string, fenced: boolean }>}
   */
  async function ask({ text, files = [], newChat = false, onStatus = () => {} }) {
    if (newChat || !win.webContents.getURL()) await win.loadURL(URL);
    await watch();
    // A new conversation starts anew; a later message goes on in the same one, with an empty box.
    const reload = () => win.webContents.loadURL(newChat ? URL : win.webContents.getURL());
    for (let attempt = 1; ; ) {
      await turn(onStatus);
      await signIn(onStatus);
      // DeepThink and Search on (user decision, 2026-10-29): search serves the 补充 a summary may add.
      await page(`(() => { for (const b of document.querySelectorAll('.ds-toggle-button')) if (!b.classList.contains('ds-toggle-button--selected')) b.click(); })()`);
      wire = { refused: false, answering: false, sent: null };
      let read;
      try {
        await compose(text, files, onStatus);
        read = await sendAndRead(onStatus, () => wrongMessage(text, files, newChat));
      } catch (error) {
        if (error.refused) {
          refused();
          await reload(); // the page stops uploading the rest
          continue;
        }
        if (!error.again || attempt >= TRIES) throw error;
        attempt += 1;
        onStatus(`${error.message}，重新发送（第 ${attempt} 次）`);
        await pause(5000);
        await reload();
        continue;
      }
      if (!read.code && BUSY.test(read.text) && read.text.length < 200) {
        if (attempt >= TRIES) throw new Error(`DeepSeek 服务器繁忙，试了 ${TRIES} 次`);
        attempt += 1;
        onStatus(`DeepSeek 服务器繁忙，${Math.round(BUSY_PAUSE_MS / 1000)} 秒后再发（第 ${attempt} 次）`);
        await pause(BUSY_PAUSE_MS);
        await reload();
        continue;
      }
      onStatus(`DeepSeek 写完了，用时 ${read.seconds} 秒`);
      return read.code ? { answer: read.code, fenced: true } : { answer: read.text, fenced: false };
    }
  }

  return {
    ask,
    stop: () => (stopped = true),
    // The window stays open, signed in, for the next conversation; after a failure it closes, as what the page holds of
    // the message that failed went into the next task's conversation (user report, 2026-10-30).
    /** @param {boolean} [failed] */
    close: (failed = false) => {
      if (win.isDestroyed()) return;
      win.webContents.debugger.removeListener('message', onRequest);
      if (failed) win.destroy();
      else idle.push(win);
    },
  };
}

module.exports = { conversation };
