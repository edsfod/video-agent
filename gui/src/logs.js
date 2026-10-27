// Log files under <userData>/logs: main.log for app events and errors, and one file per job with its full output.
// Only command lines and process output are written; stdin (where API keys travel) never is.

const fs = require('node:fs');
const path = require('node:path');

const MAIN_LIMIT = 5 * 1024 * 1024; // main.log rolls over to main.1.log at this size
const JOBS_KEPT = 200;

class Logs {
  constructor(dir) {
    this.dir = dir;
    this.jobs = path.join(dir, 'jobs');
    fs.mkdirSync(this.jobs, { recursive: true });
    this.main = path.join(dir, 'main.log');
  }

  line(level, message) {
    try {
      if (fs.existsSync(this.main) && fs.statSync(this.main).size > MAIN_LIMIT) {
        fs.renameSync(this.main, path.join(this.dir, 'main.1.log'));
      }
      fs.appendFileSync(this.main, `${new Date().toISOString()} ${level.toUpperCase().padEnd(5)} ${message}\n`);
    } catch {
      // Logging must never break the app.
    }
  }

  // Opens a job log. The first and last lines are `# {json}` so `list` can read them without parsing the output.
  job(id, meta) {
    const started = new Date();
    const stamp = started.toISOString().replace(/[-:]/g, '').replace(/\..*/, '').replace('T', '-');
    const file = path.join(this.jobs, `${stamp}-${id}.log`);
    const out = fs.createWriteStream(file, { flags: 'a' });
    out.write(`# ${JSON.stringify({ ...meta, id, started: started.toISOString() })}\n`);
    this.line('info', `job ${id} started: ${meta.title} :: ${meta.command.join(' ')}`);
    this.prune();
    return {
      file,
      write: (text) => out.write(text),
      close: (code) => {
        const seconds = Math.round((Date.now() - started) / 100) / 10;
        out.end(`\n# ${JSON.stringify({ exit: code, seconds })}\n`);
        this.line(code === 0 ? 'info' : 'warn', `job ${id} ended with exit ${code} after ${seconds}s: ${meta.title}`);
      },
    };
  }

  prune() {
    const files = fs.readdirSync(this.jobs).filter((name) => name.endsWith('.log')).sort();
    for (const name of files.slice(0, Math.max(0, files.length - JOBS_KEPT))) {
      fs.rmSync(path.join(this.jobs, name), { force: true });
    }
  }

  list() {
    return fs
      .readdirSync(this.jobs)
      .filter((name) => name.endsWith('.log'))
      .sort()
      .reverse()
      .map((name) => {
        const file = path.join(this.jobs, name);
        const text = fs.readFileSync(file, 'utf8');
        const first = text.slice(0, text.indexOf('\n'));
        const last = text.trimEnd().split('\n').pop();
        const parse = (line) => {
          try {
            return line.startsWith('# ') ? JSON.parse(line.slice(2)) : {};
          } catch {
            return {};
          }
        };
        const end = parse(last);
        return { file, ...parse(first), exit: 'exit' in end ? end.exit : null, seconds: end.seconds ?? null };
      });
  }

  read(file) {
    const target = path.resolve(file);
    if (!target.toLowerCase().startsWith(path.resolve(this.dir).toLowerCase() + path.sep)) {
      throw new Error('只能读取日志文件夹里的文件');
    }
    return fs.readFileSync(target, 'utf8');
  }
}

module.exports = { Logs };
