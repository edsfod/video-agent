// The DeepSeek route of a video summary: rounds of `pack --folder` → DeepSeek's web chat (deepseek.js) → `summarize
// --import`, the next round with `pack --follow-up`, until an answer asks for no more pictures (packing.py,
// picture_review.py). The CLI does all the summary work; this only carries the material and the answers.

const { app } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const shared = require('./shared');
const { send } = shared;
const deepseek = require('./deepseek');
const { cliCommand, runToEnd } = require('./programs');

// A runaway limit, said when reached: a chat AI that keeps asking for pictures stops here (AGENTS.md).
const MAX_ROUNDS = 6;
const SOURCE = 'DeepSeek 网页';

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
  // A first summary becomes the current one, and each later round replaces it; beside an existing summary every
  // round is kept as a version, for the user to choose, as with the other routes.
  const current = !fs.existsSync(path.join(task.folder, '总结.md'));
  let code = 0;
  try {
    for (let round = 1; ; round++) {
      if (round > MAX_ROUNDS) {
        say(`已经 ${MAX_ROUNDS} 轮，DeepSeek 还在要画面，先停在这里；最后一轮的总结已经保存。`);
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
      const { answer, fenced } = await deepseek.ask({ text, files, newChat: round === 1, onStatus: say });
      if (!fenced) say('回答没有放在代码块里，按页面上的文字导入');
      const importArgs = ['summarize', task.video, '-o', task.workspace, '--import', '-', '--source', SOURCE, '--note', `第 ${round} 轮`];
      const saved = await cli(current ? [...importArgs, '--make-current'] : importArgs, answer);
      for (const line of saved.err.split('\n').filter((item) => item.trim() && !item.includes('video-agent pack'))) say(line.trim());
      if (saved.code) {
        // The answer, to see why and to import it by hand; in the log only, as it is long.
        log.write(`\n----- 第 ${round} 轮 DeepSeek 的回答 -----\n${answer}\n----- 回答结束 -----\n`);
        throw new Error('导入失败，DeepSeek 的回答记在这个任务的日志里');
      }
      if (!saved.err.includes('--follow-up')) {
        say(round === 1 ? 'DeepSeek 没有要补的画面，完成。' : `DeepSeek 不再要画面，${round} 轮完成。`);
        break;
      }
      say('DeepSeek 要补画面，候选已截好，开始下一轮');
    }
  } catch (error) {
    code = 1;
    say(`出错：${error.message}`);
  } finally {
    fs.rmSync(work, { recursive: true, force: true });
    log.close(code);
    shared.queue.exited(task.id, code);
  }
}

module.exports = { startDeepSeek, stop: deepseek.stop };
