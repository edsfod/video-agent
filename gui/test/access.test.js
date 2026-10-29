// What the page may ask of the main process, without Electron: the CLI commands it runs itself and the paths it opens.

const test = require('node:test');
const assert = require('node:assert/strict');
const { openable, pageCommand } = require('../src/access');

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

test('the page opens files in the workspace, templates, the licence and videos, not any linked path', () => {
  const places = { workspace: 'D:\\Work', cliSettings: 'C:\\Users\\me\\AppData\\Roaming\\video-agent', files: ['C:\\VA\\resources\\LICENSE.txt', null] };
  for (const target of [
    'D:\\work\\clip-0123456789\\总结.md',
    'D:\\Work\\合集\\课',
    'C:\\Users\\me\\AppData\\Roaming\\video-agent\\templates\\标准.md',
    'C:\\VA\\resources\\LICENSE.txt',
    'E:\\Videos\\lecture.MP4',
  ]) {
    assert.ok(openable(target, places), target);
  }
  for (const target of ['C:\\Windows\\System32\\calc.exe', 'D:\\Work-other\\x.md', 'D:\\Work\\..\\x.bat', 'C:\\VA\\resources\\app.asar', '', null]) {
    assert.ok(!openable(target, places), String(target));
  }
});
