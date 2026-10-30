// The page's entry: loads every view and starts the window.

import './lists.js';
import './log-window.js';
import './settings.js';
import './summary.js';
import './terminal.js';
import { cliMismatch, loadCollections } from './collections.js';
import { renderAccounts } from './site-accounts.js';
import { $, $$, failed, state } from './state.js';
import { renderTasks } from './task-panel.js';
import { loadTemplates, renderAbout } from './templates.js';
import { renderUpdate } from './updates.js';
import { refresh, renderList, select } from './video-list.js';
import { renderTab, renderVideo } from './video-view.js';

async function init() {
  state.settings = await window.va.settings();
  state.env = await window.va.env();
  for (const button of $$('#skill-targets button[data-skill]:not([data-skill=folder])')) {
    button.title = `复制到 ${state.env.agents[button.dataset.skill].skills}`;
  }
  renderUpdate(await window.va.updateState());
  window.va.accounts().then((list) => ((state.accounts = list), renderAccounts()));
  state.videos = state.settings.videos.map((path) => ({ path, info: null }));
  state.tasks = await window.va.tasks();
  $('download-then-process').checked = state.settings.processAfterDownload !== false; // on unless turned off
  renderTasks();
  // Nothing is opened at start (user request, 2026-10-29: the first collection was). The list waits for the
  // collections, which hide their videos from 视频; drawn before, it showed every video for a moment.
  renderVideo();
  loadTemplates();
  renderAbout();
  await loadCollections();
  window.va.cliJson(['tools', '--json']).then((found) => {
    state.tools = failed(found) ? null : found;
    state.cliMismatch = cliMismatch(found);
    renderList();
    if (state.view === 'video') renderVideo();
  });
  await Promise.all(state.videos.map(refresh));
}

// For the end-to-end tests, which read the collection list again after breaking it.
window.vaPage = { loadCollections };

// Used by `electron . --screenshot=<file> --select=<n> --tab=<name>`.
window.__screenshot = async ({ select: index, tab }) => {
  await ready;
  if (index !== undefined && state.videos[Number(index)]) await select(state.videos[Number(index)].path);
  if (tab === 'logs' || tab === 'settings') return $(`open-${tab}`).click();
  if (tab) {
    state.tab = tab;
    renderTab();
  }
};

const ready = init();
