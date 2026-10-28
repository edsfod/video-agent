// The agent summary routes, run for real: Claude Code, Codex and the other agents' presets (pi, hermes, dsh). They
// spend the user's subscription or API credit, so they run only when named, as in VA_E2E_AGENTS=claude,pi.

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { _electron: electron } = require('playwright-core');

const wanted = (process.env.VA_E2E_AGENTS || '').split(',').filter(Boolean);
const GUI = path.resolve(__dirname, '..');

const OTHERS = ['pi', 'hermes', 'dsh']; // presets in main.js (AGENTS), each a route of its own once ticked in the settings

for (const agent of ['claude', 'codex', ...OTHERS]) {
  test(`summary through ${agent}`, { skip: !wanted.includes(agent) && `set VA_E2E_AGENTS=${agent}`, timeout: 600_000 }, async () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), `va-agent-${agent}-`));
    const workspace = path.join(root, 'workspace');
    const video = path.join(root, 'clip.mp4');
    execFileSync('ffmpeg', [
      '-y', '-hide_banner', '-loglevel', 'error',
      '-filter_complex', 'testsrc=duration=6:size=320x240:rate=10[v];sine=frequency=440:duration=6[s]',
      '-map', '[v]', '-map', '[s]', '-c:v', 'mpeg4', '-q:v', '3', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', video,
    ]);
    fs.writeFileSync(path.join(root, 'clip.srt'),
      '1\n00:00:00,500 --> 00:00:02,500\n这是一段测试画面\n\n2\n00:00:03,000 --> 00:00:05,000\n画面上是彩色测试图和计时器\n');
    execFileSync('video-agent', ['process', video, '-o', workspace]);
    const userData = path.join(root, 'gui-data');
    fs.mkdirSync(userData);
    const other = OTHERS.includes(agent) ? { agents: [{ key: agent }] } : {};
    fs.writeFileSync(path.join(userData, 'settings.json'), JSON.stringify({ workspace, videos: [video], ...other }));

    const app = await electron.launch({ executablePath: require('electron'), args: ['.', `--user-data=${userData}`], cwd: GUI });
    try {
      const page = await app.firstWindow();
      await page.waitForSelector('#video-list .video-item .badge:text("已处理")');
      await page.click('.tabs button[data-tab=summary]');
      await page.check(`input[name=route][value=${agent}]`);
      await page.fill('#summary-request', '写得简短一些');
      await page.click('#run-summary');
      // Wait for the job to end either way, then judge it; a failed run says why in the log.
      await page.waitForFunction(() => /·/.test(document.querySelector('#log-title').textContent), null, {
        timeout: 540_000,
      });
      const log = await page.textContent('#log-text');
      assert.match(await page.textContent('#log-title'), /· 完成$/, log.slice(-600));
      await page.waitForSelector('#summary h1');
      if (!OTHERS.includes(agent)) assert.match(log, /▸ /, 'the log shows the agent\'s commands');
      assert.match(log, /完成/);
    } finally {
      await app.close();
      fs.rmSync(root, { recursive: true, force: true });
    }
  });
}
