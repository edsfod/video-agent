# Architecture

Video Agent turns a local video into material for a summary (transcript, screen pages, representative frames) and writes or imports the summary. This page describes how it is built now. Why each part is as it is, who decided and when, is in [docs/decisions/](docs/decisions/README.md); how each release was checked is in [docs/release-log.md](docs/release-log.md); the release notes are in `docs/releases/`. Windows only.

## Parts

One core and three front ends. All media and summary work is in the Python CLI; the others start it as a process and read its output.

```text
Desktop app (gui/)          Agent skill (skills/)         Terminal
queues tasks, starts        Claude Code, Codex and        the user types
Agents and shells           other agents follow it        commands
        │                           │                         │
        └───────────────────────────┼─────────────────────────┘
                                    ▼
                     video-agent CLI (src/video_agent/)
                                    │
     ┌──────────────┬───────────────┼───────────────┬──────────────────────┐
     ▼              ▼               ▼               ▼                      ▼
   yt-dlp     FFmpeg, ffprobe   BCut (HTTP)   model APIs (HTTP)   AutoSlides Extractor
  (program)     (programs)                                        (program, optional)
```

### CLI (`src/video_agent/`)

| Module | Does |
| --- | --- |
| `cli.py` | The commands and their options, each bound to a function that runs it; prints text, or JSON with `--json`. |
| `download.py` | Runs yt-dlp: finds it, cleans share links, saves site subtitles, playlists. |
| `media.py` | Runs FFmpeg and ffprobe: probing, audio, frame sampling, screen pages, contact sheets. |
| `page_rules.py` | Which screen pages to keep, compared on small grey copies; pure functions, tested on made-up pictures. |
| `layout.py` | Finds the screen and camera regions of a video. |
| `transcript.py` | Reads, picks and writes timed subtitles. |
| `providers/bcut.py` | BCut (必剪) speech recognition over HTTP. |
| `corrections.py` | The cleaned transcript (`fix`). |
| `processor.py` | `process`: builds a video's folder, its manifest and `summary-context.md`. |
| `slide_extractor.py` | AutoSlides Extractor, and slides made already. |
| `model_api.py` | The model APIs: a `Provider` each for Anthropic and OpenAI-compatible endpoints (model list, key, one exchange with the frame tool). |
| `evidence.py` | A processed video's folder and manifest, its 视频 line, and which pictures fit a number of images. |
| `summarize.py` | `summarize` for one video with a model API. |
| `packing.py` | `pack`: the prompt for chat AIs, alone, in a zip, or in a folder of numbered pictures. |
| `importer.py` | `summarize --import`: a text written elsewhere saved as a summary or collection text, with its links and corrections repaired. |
| `collection_summary.py` | A collection's overview and study guide, from its videos' summaries. |
| `templates.py`, `prompts/` | Summary templates: the built-in ones and the user's. |
| `versions.py` | Earlier versions of a summary. |
| `collection.py` | Collections, and following a list for new videos. |
| `compress.py` | `compress`: AV1 re-encoding in place. |
| `files.py` | The per-folder lock and writes that readers never see half done. |
| `contract.py` | The types of everything printed with `--json`, of `manifest.json` and of `collection.json`. |
| `settings.py` | CLI settings and API keys (Windows Credential Manager). |

### Desktop app (`gui/`)

| File | Does |
| --- | --- |
| `src/main.js` | Main process: starts the others and the app. |
| `src/shared.js` | What its modules share: the window, tray, logs, updater, task queue, running jobs and terminals. |
| `src/settings.js` | The window's settings. |
| `src/programs.js` | Finding and running programs: the CLI, Claude Code, Codex and the other agents, shells, the plugin and licence files. |
| `src/jobs.js` | Running the queue's tasks: each kind's command line, Agent routes, cookies for downloads, follow-ups. |
| `src/plugins.js` | Installing the Agent plugin and copying the skill. |
| `src/ipc.js` | Every handler the page can call. |
| `src/window.js` | The window and the tray. |
| `src/tasks.js` | The task queue and which tasks may run together; free of Electron. |
| `src/cli-types.d.ts` | The CLI's JSON types for the app, written from `contract.py` by `scripts/cli_types.py`. |
| `src/va.d.ts` | The types of `window.va`, which `preload.js` is checked against and the page uses. |
| `src/accounts.js` | Site logins and their cookies for downloads. |
| `src/models.js` | The models and thinking levels each summary route offers. |
| `src/updater.js`, `update-plan.js`, `update-signature.js` | Updates: sources, differential downloads, the signature on `latest.yml`. |
| `src/logs.js` | The app log and one log per task. |
| `src/preload.js` | `window.va`, the page's only way to the main process. |
| `src/renderer/` | The page: `index.html`, `style.css`, and ES modules: `app.js` starts it, `state.js` holds the state and shared helpers, and one module per view (`video-list`, `video-view`, `summary`, `collections`, `lists`, `terminal`, `task-panel`, `site-accounts`, `settings`, `templates`, `updates`, `log-window`). |
| `installer/` | NSIS additions: the PATH page and script. |

### Agent skill

`skills/video-agent/SKILL.md` is a map of the CLI's commands for Agents; the plugin manifests (`.claude-plugin/`, `plugin.json`) let Claude Code and Codex install it. The desktop app copies it to other agents' skill folders.

## Data flow

1. **Download** (optional): `download URL` runs yt-dlp and saves the video and the site's subtitles to a folder (the app uses `<workspace>\下载\`). It never starts processing; the app queues `process` afterwards when 下载完自动处理 is on.
2. **Process**: `process VIDEO` reads the video and writes its folder in the workspace: the transcript (subtitles beside or inside the video, else BCut with `--allow-remote-asr`), the layout, the screen pages of the screen region, representative frames, and `summary-context.md`, which interleaves the transcript with the picture on screen.
3. **Summarize**, by one of four routes, all following the chosen template:
   - model API: `summarize` sends the transcript and pictures and writes the result;
   - Agent: Claude Code, Codex or another agent follows the skill, writes `总结.draft.md` and saves it with `summarize --import`;
   - chat AI on the web: `pack` makes the prompt, a zip or a folder; the answer comes back through `summarize --import`, which repairs its links;
   - the user's own text, through the same import.
   A new text becomes `总结.md` only when there is none or when asked; otherwise it is kept as a version.
4. **Collections**: `collection` groups videos; `summarize --collection` writes an overview or a study guide from the members' summaries.

## Files on disk

```text
<workspace>\                                  the app's default: Documents\Video Agent; the CLI's: .\video-agent-output
  下载\<title> [<id>].<ext>                   downloads made from the app, with their subtitles
  <name>-<hash>\                              one per video: name from the title, hash from the video's path
    manifest.json                             source, media facts, options, layout, pages, frames (schema_version 1)
    transcript.srt, .txt                      as acquired
    transcript.clean.srt, .txt                with corrections.json applied, when there are corrections
    frames\<run>\                             representative frames, screen\page-NNN-HH-MM-SS.jpg, layout.jpg
    frames\extra\                             frames taken later (frame, pointed-at frames, chat AI requests)
    slides\, slide-extraction\<run>\          slides, when asked for
    summary-context.md                        the material every summary route reads
    总结.md, 总结 (<time>).md, 总结.versions.json   the summary, earlier versions and their record
    .lock                                     held by process, summarize, fix
  合集\<name>\
    collection.json                           members in order, terms, skipped videos, followed source
    合集总结.md, 学习提纲.md (+ versions)       overview and study guide
    downloaded.txt                            yt-dlp's archive for a followed list
%APPDATA%\video-agent\                        CLI: settings.json, templates\, compression.json
%APPDATA%\Video Agent\                        app: settings.json, logs\, cookies\ (temporary), login partitions
```

The folder and file names, Chinese ones included, are read by the app, the skill and the links inside summaries, so renaming any of them needs a migration.

## Boundaries

- **App and CLI.** The app runs the CLI as a child process (`cli:json` parses its `--json` output, `cli:text` returns its text; API keys go on stdin). What the JSON holds is `src/video_agent/contract.py`: mypy checks the code that builds it, the tests check every value the CLI prints against it, and the app's copy, `gui/src/cli-types.d.ts`, is written from it. `tools --json` gives `json_version`, and the window says when a CLI set in the settings prints another.
- **Page and main process.** The page runs sandboxed with context isolation and a strict CSP and reaches the main process only through `window.va` (`preload.js`). Markdown is rendered with marked and sanitized with DOMPurify; `fs:read` reads only inside the workspace; `shell:open` opens any path, as a link in a summary may point anywhere (user decision).
- **Concurrency.** Jobs are separate processes that share files. The CLI locks a video's folder while writing and writes files atomically; the app's queue keeps one processing or summary task per video and limits each kind. Details: [Concurrent jobs](docs/decisions/concurrent-jobs.md).
- **Outside tools.** yt-dlp, FFmpeg and AutoSlides Extractor are run as programs, never copied in; a copy on `PATH` comes first.

## Build, release, update

- **Tests**: `tests/` (pytest and mypy; real FFmpeg on generated clips, BCut against a local server) and `gui/test/` (`node --test`; the queue rules, the updater, and Playwright end-to-end tests on the real window), after `npm run typecheck` (TypeScript checks the JavaScript through its JSDoc, without compiling it). The pre-push hook runs those a change touches; GitHub runs them by changed path (`.github/scripts/changed-jobs.sh`), Windows only.
- **Installer**: `packaging/build_cli.py` freezes the CLI with PyInstaller, yt-dlp and an LGPL FFmpeg built by `packaging/ffmpeg/build.sh`; electron-builder makes an unsigned NSIS installer that shows `PRIVACY.md` first and puts the CLI on the user's `PATH`.
- **Release**: a `v<version>` tag makes `.github/workflows/release.yml` build, test the packaged app, sign `latest.yml` with Ed25519 and create a draft with the FFmpeg sources; it is published by hand after checking.
- **Update**: the app reads `latest.yml` from github.com, the GitHub API or mirrors, accepts it only with a valid signature, downloads the changed blocks and reinstalls silently.

## Open items

- On the maintainer's machine the first two silent installs of 0.2.0 saved the PATH choice as 0 (opted out), though no choice was saved before the second; later runs of the same installer, with probes and without, and the CI test saved 1. Not explained; a test the user stopped earlier may have left a 0, which explains only the first.
- Check the Codex route after 2026-11-25.
- Code signing postponed (user decision, 2026-10-27): the SignPath application form at signpath.org/apply did not work for the user. Preparation notes are in `notes/` (local); the update signature on `latest.yml` does not depend on it.
- Representative frames can include black frames (fade-ins); detecting them needs image analysis.
- Site accounts: the cookie export, a cookies.txt import, ordering and hiding are tested (end-to-end test); a real login, Google's in particular, and a download with it need the user's account.
