// Regenerates the README screenshots: node scripts/screenshots.js <workspace> <video> [frames-dark ...]
// The video must already be processed (and summarized) in <workspace>. Use publishable content and a neutral path:
// the path, the summary and the frames all appear in the images. Writes docs/images/<view>-<theme>.webp, and
// summary-split.webp, the summary light on the left and dark on the right, for the top of the README, where every
// reader sees both (GitHub otherwise shows only the image for the reader's own theme).

const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const [workspace, video, ...only] = process.argv.slice(2); // optional: names like frames-dark to redo only those
if (!workspace || !video) {
  console.error('usage: node scripts/screenshots.js <workspace> <video>');
  process.exit(2);
}
const GUI = path.resolve(__dirname, '..');
const OUT = path.resolve(GUI, '..', 'docs', 'images');
const VIEWS = ['summary', 'process', 'frames', 'terminal'];
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'va-shots-'));
fs.mkdirSync(OUT, { recursive: true });

try {
  for (const theme of ['light', 'dark']) {
    for (const view of VIEWS) {
      if (only.length && !only.includes(`${view}-${theme}`)) continue;
      const userData = path.join(temp, `${view}-${theme}`);
      fs.mkdirSync(userData);
      // cmd without a profile, so the terminal shows nothing from the user's own shell setup.
      fs.writeFileSync(path.join(userData, 'settings.json'), JSON.stringify({ workspace, videos: [video], shell: 'cmd' }));
      const png = path.join(temp, `${view}-${theme}.png`);
      execFileSync(require('electron'), [
        '.', `--user-data=${userData}`, `--screenshot=${png}`, '--select=0', `--tab=${view}`, `--theme=${theme}`, '--wait=4000',
      ], { cwd: GUI, stdio: 'ignore' });
      if (!fs.existsSync(png)) throw new Error(`no screenshot for ${view}-${theme}`);
      const webp = path.join(OUT, `${view}-${theme}.webp`);
      execFileSync('ffmpeg', ['-y', '-hide_banner', '-loglevel', 'error', '-i', png, '-c:v', 'libwebp', '-quality', '88', webp]);
      console.log(webp, `${Math.round(fs.statSync(webp).size / 1024)} KB`);
    }
  }
  const [light, dark] = ['light', 'dark'].map((theme) => path.join(OUT, `summary-${theme}.webp`));
  const split = path.join(OUT, 'summary-split.webp');
  execFileSync('ffmpeg', [
    '-y', '-hide_banner', '-loglevel', 'error', '-i', light, '-i', dark, '-filter_complex',
    "[0:v]format=rgba[a];[1:v]format=rgba[b];[a][b]blend=all_expr='if(lt(X,W*0.5+(H*0.5-Y)*0.18),A,B)'",
    '-c:v', 'libwebp', '-quality', '88', split,
  ]);
  console.log(split, `${Math.round(fs.statSync(split).size / 1024)} KB`);
} finally {
  fs.rmSync(temp, { recursive: true, force: true });
}
