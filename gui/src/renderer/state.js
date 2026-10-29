// The page's state and the helpers every view uses. Every action runs the Video Agent CLI (or an Agent CLI) through
// window.va; nothing in the page touches media.

// An element by id. Typed loosely: each id stands for a known input, button or dialog, which the type checker cannot see.
/** @type {(id: string) => any} */
export const $ = (id) => document.getElementById(id);
/** @type {(selector: string) => NodeListOf<any>} the same for elements found by a selector */
export const $$ = (selector) => document.querySelectorAll(selector);
// Task kinds whose number at once the settings set (tasks.js DEFAULT_LIMITS).
export const LIMITED = ['download', 'process', 'summary', 'compress'];
// The version of the CLI's JSON this window reads (contract.py JSON_VERSION; tests/test_contract.py keeps them equal).
export const CLI_JSON_VERSION = 1;
/**
 * @typedef {import('../va').Va} Va
 * @typedef {import('../cli-types').Show} Show
 * @typedef {{ path: string, info: Show | null, error?: string }} Video a video in the list; info is `show`'s, once read
 * @typedef {{ id: string, xterm: import('@xterm/xterm').Terminal, fit: import('@xterm/addon-fit').FitAddon }} Term
 */
// settings and env are read first thing in init(), before anything uses them.
export const state = {
  /** @type {import('../va').Settings} */
  settings: /** @type {any} */ (null),
  /** @type {import('../va').EnvInfo} */
  env: /** @type {any} */ (null),
  /** @type {Video[]} */
  videos: [],
  /** @type {string | null} the path of the video shown */
  current: null,
  tab: 'process',
  route: 'claude',
  /** @type {any[]} */
  tasks: [], // the queue in the main process (tasks.js), without output
  /** @type {{ id: string, buffer: string, loading: boolean } | null} */
  shown: null, // { id, buffer, loading }: the task whose output the panel shows
  /** @type {Set<string>} */
  picked: new Set(), // ids of queued or running tasks ticked in the panel, to stop together
  /** @type {import('../cli-types').Collection[]} */
  collections: [], // `video-agent collection list`: each with its videos and their states
  /** @type {'video' | 'collection'} */
  view: 'video', // or 'collection', with state.collection its name
  /** @type {string | null} */
  collection: null,
  /** @type {'overview' | 'guide'} */
  doc: 'overview', // the collection file shown: overview (合集总结) or guide (学习提纲)
  /** @type {{ video: string, file: string } | null} */
  version: null, // { video, file }: a summary version shown instead of the current one
  /** @type {import('../cli-types').Tools | null} */
  tools: null, // `video-agent tools`: where FFmpeg, yt-dlp and AutoSlides Extractor were found (null: not found)
  /** @type {Term | null} */
  term: null,
  /** @type {Awaited<ReturnType<Va['accounts']>>} */
  accounts: [], // accounts.js status() of each site: { key, name, why, urls, ready, loggedIn, user? }
  /** @type {import('../cli-types').Template[]} */
  templates: [], // `video-agent template --list`: each summary template, the chosen one marked current
  /** @type {string | null} why the collection list could not be read */
  collectionsError: null,
  /** @type {string | null} what to say when the CLI's JSON is not this window's */
  cliMismatch: null,
  appVersion: '',
  /** @type {import('../cli-types').Versions | null} */
  versionList: null,
};

// ---------- helpers ----------

export function fileUrl(file) {
  const parts = file.replace(/\\/g, '/').split('/');
  return 'file:///' + [parts[0], ...parts.slice(1).map(encodeURIComponent)].join('/');
}

export function clock(seconds) {
  const total = Math.round(seconds || 0);
  const pad = (n) => String(n).padStart(2, '0');
  return `${pad(Math.floor(total / 3600))}:${pad(Math.floor((total % 3600) / 60))}:${pad(total % 60)}`;
}

export function baseName(file) {
  return file.split(/[\\/]/).pop();
}

export function joinPath(folder, relative) {
  return folder.replace(/[\\/]+$/, '') + '\\' + relative.replace(/\//g, '\\');
}

export function current() {
  return state.videos.find((video) => video.path === state.current) || null;
}

// The video whose page is open, for the buttons on that page: they can be clicked only while it is shown.
export const pageVideo = () => /** @type {Video} */ (current());

export function element(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  Object.assign(node, props);
  for (const child of [children].flat()) node.append(child);
  return node;
}

/**
 * Whether the CLI failed (cli:json answers { error }).
 * @template T
 * @param {T | import('../va').CliError} result
 * @returns {result is import('../va').CliError}
 */
export const failed = (result) => !!result && typeof result === 'object' && 'error' in result && !!result.error;

// Markdown as HTML that is safe to show: summaries, the skill, PRIVACY.md and release notes.
export const markdown = (text) => DOMPurify.sanitize(/** @type {string} */ (marked.parse(text)));
