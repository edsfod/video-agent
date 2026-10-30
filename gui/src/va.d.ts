// `window.va`: what the page can ask of the main process. preload.js implements it (and is checked against it); the
// page uses it. Return types come from the modules that answer where they can be read from them.

import type { CliOutputs } from './cli-types';
import type * as accounts from './accounts.js';
import type * as models from './models.js';
import type { TaskQueue } from './tasks.js';
import type { createUpdater } from './updater.js';
import type { Logs } from './logs.js';

type Answer<F extends (...args: any) => any> = Promise<Awaited<ReturnType<F>>>;
type Listener<T> = (callback: (value: T) => void) => () => void;

/** The window's settings (settings.js `defaults()` and what the window saves). */
export interface Settings {
  workspace: string;
  cli: string;
  videos: string[];
  frameInterval: number;
  maxFrames: number | null;
  shell: string;
  closeToTray: boolean;
  checkUpdates: boolean;
  betaUpdates?: boolean;
  updateMirror: string;
  limits: Record<string, number>;
  processAfterDownload: boolean;
  compressDownloads: boolean;
  compressLocal: boolean;
  bcut: boolean;
  extractor: boolean;
  /** Other agents shown as summary routes; null shows the presets found on this computer. */
  agents: { key: string; command?: string }[] | null;
  webFiles: number;
  webRounds: number;
  theme?: 'system' | 'light' | 'dark';
  accountOrder?: string[];
  hiddenAccounts?: string[];
  routeModels?: Record<string, string>;
  routeEfforts?: Record<string, string>;
  lastUpdateCheck?: unknown;
  lastVersion?: string;
  skillCopies?: string[];
}

export interface OtherAgent {
  key: string;
  name: string;
  command: string;
  file: string;
  args: string[];
  found: boolean;
  model: boolean;
}

/** An agent preset (programs.js AGENTS): its name, command line, whether it is installed, where it reads skills. */
export interface Preset {
  name: string;
  command: string;
  found?: boolean;
  skills?: string;
}

export interface EnvInfo {
  cli: string[];
  claude: string | null;
  codex: string | null;
  others: OtherAgent[];
  agents: Record<string, Preset>;
  shells: { id: string; label: string }[];
  pluginRoot: string;
  bundled: boolean;
}

export interface AboutInfo {
  version: string;
  privacy: string;
  license: string | null;
  notices: string | null;
}

/** A CLI run to its end: exit code (-1 when it could not start), standard output and standard error. */
export interface RunResult {
  code: number | null;
  out: string;
  err: string;
}

/** The answer of `cliJson` when the CLI failed or printed no JSON. */
export interface CliError {
  error: string;
}

export interface Outcome {
  ok: boolean;
  output: string;
}

type Updater = ReturnType<typeof createUpdater>;

export interface Va {
  settings(): Promise<Settings>;
  saveSettings(changes: Partial<Settings>): Promise<Settings>;
  previewTheme(theme: string): Promise<string>;
  env(): Promise<EnvInfo>;
  installPlugin(agent: string): Promise<Outcome>;
  readSkill(): Promise<string>;
  about(): Promise<AboutInfo>;
  accounts(): Answer<typeof accounts.list>;
  accountLogin(key: string): Answer<typeof accounts.login>;
  accountLogout(key: string): Answer<typeof accounts.logout>;
  accountImport(key: string): Promise<Awaited<ReturnType<typeof accounts.importCookies>> | null>;
  browsers(): Answer<typeof accounts.browsers>;
  accountFromBrowser(key: string, browser: string): Promise<Awaited<ReturnType<typeof accounts.importCookies>> | CliError>;
  updateState(): Answer<Updater['state']>;
  checkUpdate(): Answer<Updater['check']>;
  downloadUpdate(): Answer<Updater['download']>;
  installUpdate(force?: boolean): Answer<Updater['install']>;
  onUpdateState: Listener<ReturnType<Updater['state']>>;
  downloadExtractor(): Promise<{ path: string; version: string }>;
  onExtractorProgress: Listener<{ source: string; received: number; total: number }>;
  pickVideos(): Promise<string[]>;
  pickFolder(title: string): Promise<string | null>;
  pickFile(title: string, filters: { name: string; extensions: string[] }[]): Promise<string | null>;
  pickSave(title: string, name: string): Promise<string | null>;
  droppedPath(file: File): string;

  addTask(spec: { kind: string; title: string; [field: string]: unknown }): Answer<TaskQueue['add']>;
  tasks(): Answer<TaskQueue['list']>;
  taskOutput(id: string): Promise<[stream: string, text: string][]>;
  cancelTask(id: string | string[]): Promise<void>;
  retryTask(id: string): Answer<TaskQueue['retry']>;
  models(route: string): Answer<typeof models.list>;
  installSkill(target: string): Promise<Outcome | null>;
  clearTasks(): Answer<TaskQueue['clearFinished']>;
  onTasks: Listener<ReturnType<TaskQueue['list']>>;
  onJobOutput: Listener<{ id: string; stream: string; text: string }>;
  /** Runs the CLI and parses what it prints; a command named first gets the type of its output. `if (result.error)`
   * tells a failure from it. */
  cliJson<C extends keyof CliOutputs>(args: [C, ...string[]]): Promise<(CliOutputs[C] & { error?: undefined }) | CliError>;
  cliText(args: string[], stdin?: string): Promise<RunResult>;

  read(file: string): Promise<string | null>;
  open(target: string): Promise<string>;
  reveal(target: string): Promise<void>;
  external(url: string): Promise<unknown>;
  copy(text: string): Promise<void>;

  logs(): Answer<Logs['list']>;
  readLog(file: string): Answer<Logs['read']>;
  openLogs(): Promise<string>;
  logError(message: unknown): void;
  onTrayAddVideos: Listener<void>;

  ptyStart(options: { id: string; shellId: string; cwd: string; cols: number; rows: number }): Promise<string>;
  ptyWrite(id: string, data: string): void;
  ptyResize(id: string, cols: number, rows: number): void;
  ptyKill(id: string): Promise<void>;
  onPtyData: Listener<{ id: string; data: string }>;
  onPtyExit: Listener<{ id: string; exitCode: number }>;
}
