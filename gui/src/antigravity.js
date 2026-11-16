// The Antigravity route (user request, 2026-11-16: 「新增一条 Antigravity 路线，自动调用，使用 gemini-3.8-flash-high」): the
// task an Agent gets (read the skill, save through `summarize --import`) goes to the agent of the Antigravity desktop app
// that is running, as a new conversation there, which the user can watch in the app.
//
// How, read from the app on the maintainer's machine (Antigravity 44.9.1, its language server 2.32.1; none of it is
// documented): the app ships `language_server.exe agentapi new-conversation [--model=<id>] [--title=<t>] <prompt>`,
// which needs the running server's address and CSRF token in ANTIGRAVITY_LS_ADDRESS and ANTIGRAVITY_CSRF_TOKEN; the
// server writes both to ~/.gemini/antigravity/daemon/hub_<port>.json. The command returns the conversation's id at
// once. The same server answers Connect JSON calls on that port with the token in x-codeium-csrf-token:
// GetCascadeTrajectory gives the steps and a run status (RUNNING, then IDLE when the agent has finished),
// GetCascadeModelConfigData the models with their ids (gemini-3.8-flash-high among them), ForceStopCascadeTree
// ({conversationId}) stops one. Tried 2026-11-16: an agent so started ran a command and wrote a file without asking,
// summarized a test video and saved it through `summarize --import`; a stop took effect within seconds. A command the
// agent moves to the background may still show as running after the conversation is IDLE.

const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');

const DEFAULT_MODEL = 'gemini-3.8-flash-high'; // the user's choice, 2026-11-16
const POLL_MS = 5000;
const DAEMON = () => path.join(os.homedir(), '.gemini', 'antigravity', 'daemon');

/** The app's language server, in its install folder (from the uninstall entry, any drive) or the default one. */
function server() {
  const { installFolders } = require('./programs');
  return installFolders('Antigravity')
    .map((folder) => path.join(folder, 'resources', 'bin', 'language_server.exe'))
    .find((file) => fs.existsSync(file)) || null;
}

const alive = (pid) => {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
};

/** The running server's port and token: the newest record whose process is still there. */
function hub() {
  let records = [];
  try {
    records = fs.readdirSync(DAEMON()).filter((name) => /^hub_\d+\.json$/.test(name)).map((name) => path.join(DAEMON(), name));
  } catch {
    return null;
  }
  records.sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs);
  for (const file of records) {
    try {
      const record = JSON.parse(fs.readFileSync(file, 'utf8'));
      if (record.httpPort && record.csrfToken && alive(record.pid)) return record;
    } catch {
      // a record being written, or an old one
    }
  }
  return null;
}

/** @returns {Promise<any>} */
function rpc(found, method, body) {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify(body);
    const request = http.request({
      host: '127.0.0.1',
      port: found.httpPort,
      method: 'POST',
      path: `/exa.language_server_pb.LanguageServerService/${method}`,
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data), 'x-codeium-csrf-token': found.csrfToken },
      timeout: 30_000,
    }, (response) => {
      let text = '';
      response.on('data', (chunk) => (text += chunk));
      response.on('end', () => {
        if (response.statusCode !== 200) return reject(new Error(`Antigravity ${method}: ${response.statusCode} ${text.slice(0, 200)}`));
        try {
          resolve(JSON.parse(text));
        } catch (error) {
          reject(error);
        }
      });
    });
    request.on('timeout', () => request.destroy(new Error(`Antigravity ${method}: no answer`)));
    request.on('error', reject);
    request.end(data);
  });
}

/** The models the app offers, each by id and its label there. */
async function models() {
  const found = hub();
  if (!found) return { models: [], efforts: [], error: 'Antigravity 没有在运行，打开它再试' };
  const data = await rpc(found, 'GetCascadeModelConfigData', {});
  const list = (data.clientModelConfigs || []).filter((model) => model.modelId && !model.disabled);
  return { models: list.map((model) => ({ value: model.modelId, label: `${model.label}（${model.modelId}）` })), efforts: [] };
}

/** One line for a step of the agent's, or null for those not worth showing. */
function stepLine(step) {
  const kind = String(step.type || '').replace('CORTEX_STEP_TYPE_', '');
  if (/WAIT/.test(String(step.status))) return `等你在 Antigravity 里确认：${kind}`;
  if (kind === 'PLANNER_RESPONSE') {
    const text = step.plannerResponse?.modifiedResponse || step.plannerResponse?.response || '';
    return text.trim() ? text.trim() : null;
  }
  if (kind === 'RUN_COMMAND') {
    const line = step.runCommand?.commandLine || '';
    return `▸ ${line.length > 300 ? `${line.slice(0, 300)}…` : line}`;
  }
  if (kind === 'VIEW_FILE') return `▸ 读 ${decodeURIComponent(String(step.viewFile?.absolutePathUri || '').replace(/^file:\/\/\//, ''))}`;
  if (kind === 'GENERIC') {
    // Tools without a step type of their own (writing a file, a command run through a hook) carry their arguments.
    const args = step.generic?.args || {};
    const what = args.toolSummary || args.CommandLine || args.TargetFile || '';
    return what ? `▸ ${String(what).slice(0, 300)}` : null;
  }
  if (kind === 'USER_INPUT' || kind === 'SYSTEM_MESSAGE' || kind === 'CHECKPOINT') return null;
  return `▸ ${kind.toLowerCase()}`;
}

/**
 * Starts the task in Antigravity and follows it to the end.
 * @param {{ id: string, model?: string, title: string }} task
 * @param {string} prompt
 * @param {{ say: (text: string) => void, done: (code: number) => void, saved: () => Promise<boolean> }} hooks
 * @returns {{ stop: () => void }}
 */
function run(task, prompt, { say, done, saved }) {
  let cascade = null;
  let stopping = false;
  let finished = false;
  const end = (code) => {
    if (finished) return;
    finished = true;
    done(code);
  };
  const exe = server();
  const found = hub();
  if (!exe || !found) {
    say(!exe ? '没有找到 Antigravity 桌面版。\n' : 'Antigravity 没有在运行：打开它（登录好）再试。\n');
    setImmediate(() => end(1));
    return { stop: () => {} };
  }
  const model = task.model || DEFAULT_MODEL;
  const env = { ...process.env, ANTIGRAVITY_LS_ADDRESS: `localhost:${found.httpPort}`, ANTIGRAVITY_CSRF_TOKEN: found.csrfToken };
  const child = spawn(exe, ['agentapi', 'new-conversation', `--model=${model}`, `--title=${task.title}`, prompt], { env, windowsHide: true });
  let out = '';
  child.stdout.on('data', (chunk) => (out += chunk));
  child.stderr.on('data', (chunk) => (out += chunk));
  child.on('error', (error) => {
    say(`${error.message}\n`);
    end(1);
  });
  child.on('close', () => {
    let answer;
    try {
      answer = JSON.parse(out);
    } catch {
      answer = { error: out.trim() || 'agentapi 没有回答' };
    }
    cascade = answer.response?.newConversation?.conversationId;
    if (!cascade) {
      say(`Antigravity 没有开始：${answer.error || out.trim()}\n`);
      return end(1);
    }
    say(`已在 Antigravity 里开始（模型 ${model}），可以在它的窗口里看。\n`);
    if (stopping) stop();
    follow();
  });

  const shown = new Set();
  let ran = false;
  async function follow() {
    while (!finished) {
      await new Promise((resolve) => setTimeout(resolve, POLL_MS));
      if (finished) return;
      let data;
      try {
        data = await rpc(found, 'GetCascadeTrajectory', { cascadeId: cascade });
      } catch (error) {
        if (!alive(found.pid)) {
          say('Antigravity 关掉了，任务没有做完。\n');
          return end(1);
        }
        say(`读不到 Antigravity 的进度，再试：${error.message}\n`);
        continue;
      }
      const steps = data.trajectory?.steps || [];
      // A step is shown once it is done; one waiting for the user, each time it is seen.
      steps.forEach((step, index) => {
        const status = String(step.status);
        if (shown.has(index) || !(status.endsWith('DONE') || /WAIT/.test(status))) return;
        const line = stepLine(step);
        if (line) say(`${line}\n`);
        if (status.endsWith('DONE')) shown.add(index);
      });
      if (data.status === 'CASCADE_RUN_STATUS_RUNNING') ran = true;
      if (data.status === 'CASCADE_RUN_STATUS_IDLE' && (ran || steps.length > 1)) {
        if (stopping) return end(-1);
        const ok = await saved();
        say(ok ? '总结已保存。\n' : 'Antigravity 停下了，但没有保存总结（看上面它说了什么）。\n');
        return end(ok ? 0 : 1);
      }
    }
  }

  function stop() {
    stopping = true;
    if (!cascade) return;
    rpc(found, 'ForceStopCascadeTree', { conversationId: cascade })
      .catch((error) => say(`没能让 Antigravity 停下：${error.message}\n`))
      .finally(() => setTimeout(() => end(-1), 3000));
  }
  return { stop };
}

module.exports = { DEFAULT_MODEL, models, run, server, stepLine };
