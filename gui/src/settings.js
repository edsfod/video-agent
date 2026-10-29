// The window's settings, in <userData>/settings.json.

const { app } = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const { DEFAULT_LIMITS } = require('./tasks');

// 外观 in the settings (user request, 2026-10-28): follow Windows, or always light or dark.
const THEMES = ['system', 'light', 'dark'];
const settingsFile = () => path.join(app.getPath('userData'), 'settings.json');
// Cookies exported for one download at a time; removed when the download ends and at start (after a crash).
const cookiesDir = () => path.join(app.getPath('userData'), 'cookies');

function defaults() {
  return {
    workspace: path.join(app.getPath('documents'), 'Video Agent'),
    cli: '',
    videos: [],
    frameInterval: 60,
    maxFrames: null, // representative frames: no fixed cap unless the user sets one
    shell: '',
    closeToTray: true,
    checkUpdates: true,
    updateMirror: '',
    limits: DEFAULT_LIMITS, // tasks of each kind that may run at once (see tasks.js)
    processAfterDownload: true, // downloaded files are processed, so their subtitles are imported at once
    // Compressing replaces the file (user decision, 2026-10-28): on for this program's downloads, off for videos added
    // from disk until the user agrees to have them replaced.
    compressDownloads: true,
    compressLocal: false,
    // A video without subtitles is transcribed with BCut, which uploads its audio to Bilibili: on unless the user turns
    // it off, also for videos processed after a download (user decision, 2026-10-28). The CLI still needs the flag.
    bcut: true,
    // Other agents shown as summary routes, [{ key, command }]: a key of AGENTS or 'custom', and its command line, where
    // {prompt} stands for the task if it takes no standard input. null shows the presets found on this computer.
    agents: null,
    webFiles: 50, // files a chat AI takes at once, for 导出文件夹 (DeepSeek's web chat: 50)
  };
}

function loadSettings() {
  let saved;
  try {
    saved = JSON.parse(fs.readFileSync(settingsFile(), 'utf8'));
  } catch {
    return defaults();
  }
  // Up to 0.2.0 every processing run saved the old fixed cap of 36 frames; it was not a choice, so it no longer caps.
  if (saved.maxFrames === 36) saved.maxFrames = null;
  // 0.8.2 and 0.8.3 kept one other agent, or none, as `agent` and `agentCommand`.
  if (!('agents' in saved) && 'agent' in saved) saved.agents = saved.agent ? [{ key: saved.agent, command: saved.agentCommand || '' }] : null;
  delete saved.agent;
  delete saved.agentCommand;
  return { ...defaults(), ...saved };
}

function saveSettings(changes) {
  const next = { ...loadSettings(), ...changes };
  fs.mkdirSync(path.dirname(settingsFile()), { recursive: true });
  fs.writeFileSync(settingsFile(), JSON.stringify(next, null, 2));
  return next;
}

module.exports = { THEMES, cookiesDir, loadSettings, saveSettings };
