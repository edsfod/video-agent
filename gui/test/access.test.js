// Which CLI commands the page may run itself, without Electron.

const test = require('node:test');
const assert = require('node:assert/strict');
const { pageCommand } = require('../src/access');

test('the page runs reading and editing commands, and the rest only through the queue', () => {
  for (const args of [
    ['show', 'D:\\v.mp4', '-o', 'D:\\work'],
    ['collection', 'list', '-o', 'D:\\work'],
    ['template', '--list'],
    ['compress', '--check', '--json', 'D:\\v.mp4'],
    ['summarize', 'D:\\v.mp4', '--import', '-'],
  ]) {
    assert.ok(pageCommand(args), args.join(' '));
  }
  for (const args of [
    ['download', 'https://example.com/v'],
    ['process', 'D:\\v.mp4'],
    ['compress', 'D:\\v.mp4'],
    ['summarize', 'D:\\v.mp4'],
    ['collection', 'update', '课'],
    ['_yt-dlp', '--exec', 'calc'],
    [],
    ['show', 3],
    'show',
  ]) {
    assert.ok(!pageCommand(args), JSON.stringify(args));
  }
});
