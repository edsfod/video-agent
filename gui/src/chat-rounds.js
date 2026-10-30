// The DeepSeek route of a video summary: rounds of `pack --folder` → DeepSeek's web chat (deepseek.js) → `summarize
// --import`, the next round with `pack --follow-up` while the import asks for one: a 复查 of the draft, what the checks
// found, pictures wanted (summary_review.py, picture_review.py). The CLI does all the summary work; this only carries
// the material and the answers. Each task has a conversation, in a window, of its own, so several run at once.

const { app } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const shared = require('./shared');
const { send } = shared;
const deepseek = require('./deepseek');
const { cliCommand, runToEnd } = require('./programs');

// A runaway limit, said when reached: a chat AI whose 复查 keeps finding something stops here (AGENTS.md).
const MAX_ROUNDS = 6;
const SOURCE = 'DeepSeek 网页';
/** The conversations of the running tasks, by task id. @type {Map<string, ReturnType<typeof deepseek.conversation>>} */
const running = new Map();

/** @param {string[]} args @param {string} [stdin] */
function cli(args, stdin) {
  const [command, ...prefix] = cliCommand();
  return runToEnd(command, [...prefix, ...args], stdin);
}

async function startDeepSeek(task) {
  const log = shared.logs.job(task.id, { title: task.title, command: [SOURCE], cwd: task.workspace });
  const say = (line) => {
    const text = `${line}\n`;
    log.write(text);
    shared.queue.output(task.id, 'stdout', text);
    send('job:output', { id: task.id, stream: 'stdout', text });
  };
  const work = fs.mkdtempSync(path.join(app.getPath('temp'), 'video-agent-deepseek-'));
  // A first summary becomes the current one; beside an existing summary it is a version, for the user to choose, as
  // with the other routes. Either way each later round overwrites the one before (the import sees to it).
  const current = !fs.existsSync(path.join(task.folder, '总结.md'));
  const chat = deepseek.conversation();
  running.set(task.id, chat);
  let code = 0;
  try {
    for (let round = 1; ; round++) {
      if (round > MAX_ROUNDS) {
        say(`已经 ${MAX_ROUNDS} 轮，DeepSeek 的复查还在补上或改正，先停在这里；最后一轮的总结已经保存。`);
        break;
      }
      const args = ['pack', task.video, '-o', task.workspace, '--folder', work, '--max-files', String(task.maxFiles || 50)];
      if (round > 1) args.push('--follow-up');
      else {
        if (task.template) args.push('--template', task.template);
        if (task.request) args.push('--request', task.request);
      }
      const packed = await cli(args);
      if (packed.code) throw new Error((packed.err || packed.out).trim());
      const folder = packed.out.trim().split('\n').pop().replace(/ \(\d+ pictures\)$/, '');
      const files = fs.readdirSync(folder).filter((name) => name !== '提示词.md').sort().map((name) => path.join(folder, name));
      say(`第 ${round} 轮：发给 DeepSeek，附 ${files.length} 张图`);
      const text = fs.readFileSync(path.join(folder, '提示词.md'), 'utf8');
      const { answer, fenced } = await chat.ask({ text, files, newChat: round === 1, onStatus: say });
      if (!fenced) say('回答没有放在代码块里，按页面上的文字导入');
      const importArgs = ['summarize', task.video, '-o', task.workspace, '--import', '-', '--source', SOURCE, '--note', `第 ${round} 轮`];
      if (task.template) importArgs.push('--template', task.template); // the sections the import checks for
      const saved = await cli(current ? [...importArgs, '--make-current'] : importArgs, answer);
      for (const line of saved.err.split('\n').filter((item) => item.trim() && !item.includes('video-agent pack'))) say(line.trim());
      if (saved.code) {
        // The answer, to see why and to import it by hand; in the log only, as it is long.
        log.write(`\n----- 第 ${round} 轮 DeepSeek 的回答 -----\n${answer}\n----- 回答结束 -----\n`);
        throw new Error('导入失败，DeepSeek 的回答记在这个任务的日志里');
      }
      if (!saved.err.includes('--follow-up')) {
        say(`这一稿没有再补上或改正什么，检查也都通过，${round} 轮完成。`);
        break;
      }
      say('开始下一轮');
    }
  } catch (error) {
    code = 1;
    say(`出错：${error.message}`);
  } finally {
    running.delete(task.id);
    chat.close();
    fs.rmSync(work, { recursive: true, force: true });
    log.close(code);
    shared.queue.exited(task.id, code);
  }
}

/** @param {string} id */
const stop = (id) => running.get(id)?.stop();

module.exports = { startDeepSeek, stop };
