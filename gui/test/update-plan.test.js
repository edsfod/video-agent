// Joining nearby changed blocks into one range for the differential download, without Electron.

const test = require('node:test');
const assert = require('node:assert/strict');
const plan = require('electron-updater/out/differentialDownloader/downloadPlanBuilder');
const { mergeNearby, install } = require('../src/update-plan');

const compute = plan.computeOperations; // electron-updater's own plan, before install() wraps it

const KB = 1024;
// One file of `count` blocks of 20 KB; the new one changes the blocks at `changed`.
function maps(count, changed) {
  const sizes = Array(count).fill(20 * KB);
  const checksums = sizes.map((_, i) => `b${i}`);
  const file = (sums) => ({ version: '2', files: [{ name: 'file', offset: 0, checksums: sums, sizes }] });
  return [file(checksums), file(checksums.map((sum, i) => (changed.includes(i) ? `new${i}` : sum)))];
}
const logger = { info() {}, warn() {} };
const downloads = (operations) => operations.filter((operation) => operation.kind === plan.OperationKind.DOWNLOAD);
const size = (operations) => operations.reduce((sum, operation) => sum + operation.end - operation.start, 0);

test('changed blocks a few blocks apart become one range; far apart they stay apart', () => {
  // 3 and 5 are 20 KB apart, 5 and 200 about 3.8 MB.
  const [old, next] = maps(300, [3, 5, 200]);
  const original = compute(old, next, logger);
  const merged = mergeNearby(original);
  assert.equal(downloads(original).length, 3);
  assert.deepEqual(downloads(merged).map(({ start, end }) => [start / KB, end / KB]), [[60, 120], [4000, 4020]]);
  assert.equal(size(merged), size(original), 'every byte of the new file is still downloaded or copied once');
});

test('installed, electron-updater plans the joined ranges', () => {
  install();
  install(); // once only
  const [old, next] = maps(100, [10, 12, 14]);
  const operations = plan.computeOperations(old, next, logger);
  assert.equal(downloads(operations).length, 1);
  assert.deepEqual([operations[1].start, operations[1].end], [200 * KB, 300 * KB]);
});
