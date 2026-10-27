# Architecture

Status: CLI phase 1 implemented and verified end to end on one Bilibili video on 2026-10-26 (download, BCut transcription, representative frames, summary context). `summarize`, the Agent skill and the GUI are implemented and tested (2026-10-27); see "Status and open items". Nothing is released until the user says so (user decision, 2026-10-27).

## Platform — user decision

Windows only (user decision, 2026-10-27). Linux and macOS are not supported or tested; CI runs on Windows only.

## Product boundary

The product summarizes local video files regardless of source. Users can select an already-downloaded file directly. An optional `download` command can acquire a video from a supported URL, but downloading ends at a local file path; the user then invokes `process` separately. `process` never downloads implicitly.

## Parts

These parts divide the work by responsibility; additions beyond the user's stated requirements are marked.

1. **Acquisition** accepts an existing local file or, when requested, uses a downloader adapter to create one. The first adapter is yt-dlp. It is optional and separate from processing.
2. **Input and provenance** validates a local video path and records the source path, media facts, selected options, and completed artifacts in a per-video manifest. It never moves or rewrites the source video. **Added:** the manifest makes repeated runs traceable.
3. **Media inspection** discovers audio, video, and subtitle streams and extracts audio needed for recognition. FFmpeg and ffprobe stay behind this boundary.
4. **Transcript acquisition** produces timed text. It checks usable sidecar and embedded subtitles before an ASR provider. Subtitle parsing, correction, search, and export remain independent of a provider. Remote ASR requires an explicit command-line consent flag.
5. **Representative frames** provide visual evidence independently of slide extraction. A bounded sampler combines regular intervals with scene-change candidates, removes exact duplicate images, and records timestamps. This runs when slide extraction is off. **Added:** it covers silent and visually dense videos; scene changes are candidates, not semantic judgments.
6. **Optional slide extraction** is a separate adapter to AutoSlides Extractor. The CLI invokes its local command-line mode only when the user passes `--extract-slides`; default is off. It writes slide images and a timeline map in a separate output directory. Representative-frame sampling remains independent.
7. **Evidence and summarization** writes `summary-context.md` with timed transcript text and image references. The CLI does not call a language model. The Agent skill `skills/video-agent/` writes `总结.md` from this evidence, adapted from the upstream yanhe-agent skill: the generic template replaces the lecture template, which remains a variant for lecture recordings. `frame` saves extra frames at times the Agent chooses. **Claude judgment:** a skill rather than a model API in the CLI keeps the core free of model-provider dependencies.
8. **Artifacts and jobs** store results in a workspace associated with the selected video. Source videos remain untouched. **Added:** the same artifacts can be consumed by the CLI now and a GUI later.

## Downloader decision — Claude judgment

Use yt-dlp as the optional download backend. Its official project is a command-line downloader with broad site support and documents both stable CLI output (`--print after_move:filepath`) and a Python embedding API. The project can therefore call it as a separate process and receive the final saved path without parsing human-oriented progress text.

Do not use Media Downloader as the backend. Its repository describes it as a Qt/C++ GUI front end whose default engine is yt-dlp; it is useful as a standalone graphical downloader, but it is a second interface rather than the download engine this CLI needs. The new project will keep its own planned GUI over the shared processing modules.

This choice adds one optional `download` subcommand and an external yt-dlp requirement. It does not change `process` input: `process` continues to accept local paths only. Downloads are never chained automatically into transcription or summarization. The current Media Downloader-managed executable is auto-detected from the user's AppData directory; Video Agent does not install or update it. Since 0.1.1 yt-dlp is also a Python dependency (see "Distribution"), so `download` works out of the box; a yt-dlp on `PATH` or Media Downloader's copy still comes first.

## Interface sequence — user decision

Build the CLI first and write the operating documentation. On 2026-10-27 the user brought the GUI back into scope (it had been deferred on 2026-10-26); see "GUI". The CLI means text commands typed in PowerShell or another terminal; it is the first implementation interface, not a requirement that the project remain command-line-only. A GUI will select local files, show the default-off slide option, report progress, and open results by calling the same processing modules.

The current CLI also serves batch processing and future Agent integration. Do not put media processing logic in the GUI or an Agent skill. Do not add a resident MCP server in this phase.

## GUI — user decision, Claude judgment on technology

Implemented in `gui/` (2026-10-27). The first release ships the CLI, skill and GUI together. Scope the user set on 2026-10-27: the GUI calls the same CLI for all media work and supports every summary route side by side, plus an embedded terminal.

- **Summary routes.** (1) Headless Agent: run Claude Code (`claude -p`) or Codex (`codex exec`) with the `video-agent` skill; uses the user's existing subscription and can take extra frames. (2) Model API: an optional CLI `summarize` command sends the transcript and representative frames to a configured vision-capable model (Anthropic, or any OpenAI-compatible endpoint such as a local Ollama); it takes extra frames through tool calling where the provider and model support it (the model asks for a time, `summarize` runs `frame` and sends the image back, and the model continues), and otherwise works from the pre-sampled frames only. Keys live in Windows Credential Manager, never in plain files. (3) Copy material: put `summary-context.md` on the clipboard for any chat AI. All routes use the same rules and template, `src/video_agent/prompts/summary.md` (printed by `video-agent template`), so their output has the same shape. Both `summarize` and the GUI are implemented.
- **Embedded terminal.** A terminal panel with a shell the user picks from those installed: PowerShell 7, Windows PowerShell 5.1, Command Prompt, Git Bash. It opens in the video's workspace folder and can run the CLI or an interactive `claude`/`codex` session.
- **Technology (Claude judgment).** Electron, like the AutoSlides app, with xterm.js and node-pty for the terminal (the combination VS Code uses on Windows through ConPTY). Qt, which AutoSlides Extractor uses, has no maintained terminal widget, so the terminal requirement favours Electron. The GUI starts the CLI as a subprocess; no media or summary logic lives in the front end.


```text
video-agent download <URL>... [download options]
video-agent inspect <local-video-path>
video-agent process <local-video-path>... [--extract-slides]
video-agent frame <local-video-path> <time>... [-o <workspace>]
```

`download` prints the resulting local file paths. `process` is a separate command; it obtains local or explicitly requested remote transcript data, samples representative frames, and writes an evidence bundle. `--extract-slides` opts into AutoSlides Extractor. The source video remains in place.

## First implementation boundary

Keep the generic core free of Yanhekt, BIT SSO, and course identifiers. Keep yt-dlp and AutoSlides Extractor behind replaceable executable adapters, not platform-specific processing logic. AutoSlides Extractor is not bundled; yt-dlp and FFmpeg are, since 0.1.1 (see "Distribution"). No GUI dependency belongs in the CLI core, and the core runs without any model provider; `summarize` loads a provider only when it is invoked.

## Distribution — user decision (2026-10-27, 0.1.1)

The 0.1.0 install asked for uv, FFmpeg and, without saying so, git (`uv tool install git+https://…` fails without it). The user chose to remove these steps:

- **Dependencies.** FFmpeg comes from `imageio-ffmpeg` and yt-dlp from PyPI, both declared in `pyproject.toml`. Tools on `PATH` are preferred. `imageio-ffmpeg` has no ffprobe, so `media.probe` reads the needed facts (streams, codecs, languages, duration) from ffmpeg's banner when ffprobe is missing; a test checks both give the same answer. `download` passes `--ffmpeg-location` so yt-dlp merges streams with the same ffmpeg.
- **No git.** The README, the skill and the GUI's last-resort `uvx` use the wheel attached to the GitHub release instead of a `git+` URL. Installing the Agent plugin from GitHub with `claude`/`codex plugin marketplace add edsfod/video-agent` still needs git (both fail with git hidden from `PATH`, checked 2026-10-27), so the desktop app has buttons that install it from its local copy.
- **Desktop installer bundles everything.** `packaging/build_cli.py` freezes the CLI with PyInstaller (Python, ffmpeg, yt-dlp; about 118 MB) into `resources/cli`; the installer grew from 126 MB to 167 MB and needs no network. A frozen build has no `python -m`, so the bundled yt-dlp runs as `video-agent _yt-dlp`. The GUI uses a CLI set in its settings first, then the bundled one, then `video-agent` on `PATH`; its jobs and terminals see the bundled folder first on `PATH`.
- **PATH and shortcuts.** The installer appends `resources\cli` to the user's `PATH` and the uninstaller removes it (`gui/installer/`). Desktop and Start menu shortcuts are electron-builder's defaults. **Claude judgment:** appending, not prepending, keeps a CLI the user installed themselves first in terminals. The script edits `HKCU\Environment` through the registry API with `DoNotExpandEnvironmentNames` and keeps the value type, because `[Environment]::GetEnvironmentVariable` returns expanded text and writing it back would turn entries like `%USERPROFILE%\bin` into fixed paths. Checked on 2026-10-27 with silent install and uninstall: `PATH` came back byte-identical and both shortcuts were removed.

## Status and open items

Done and checked (2026-10-26 and 2026-10-27):

- End-to-end CLI run on a Bilibili video: download, BCut transcription, frames, summary context. The user decided AutoSlides Extractor needs no separate verification.
- Summary skill: a headless Claude Code run loaded it as a plugin (`claude -p --plugin-dir`) and wrote `总结.md` (24 turns, about USD 0.71). Plugin manifests pass `claude plugin validate`, also in the packaged build.
- `summarize`: wrote `总结.md` with ModelScope `Qwen/Qwen3.5-397B-A17B`; one real frame-tool round trip passed. The Anthropic route is tested against a fake server only. Probed: NVIDIA `nemotron-3.5-super-vl` returned empty text for an image within 200 tokens; Z.ai vision models answered 余额不足; ModelScope InternVL3.5 answered token expired.
- GUI (`gui/`, Electron 45, xterm.js 6, node-pty 1.1) with tray and logs. Tray (user request): closing the window hides it while jobs keep running (setting, on by default); a second launch shows the existing window. Logs (user request): `<userData>/logs/main.log` (rolls at 5 MB) and one file per job (newest 200), viewable in the 日志 window; stdin, where API keys travel, is never written. No notifications or balloons (the user rejected them).
- GUI routes run for real: Claude Code wrote a summary from the window (about 35 s). Codex could not be checked: the account's usage limit runs until 2026-11-25; the window now shows the agent's error instead of a bare exit code.
- Tests: 33 pytest tests, including one that keeps the version equal across `pyproject.toml`, the plugin manifests, `gui/package.json`, the skill and the README; 10 GUI end-to-end tests (`gui/test/e2e.test.js`, Playwright) pass from source and against the unpacked build, which CI builds and tests in the `installer` job; `gui/test/agents.test.js` runs the real agent routes only with `VA_E2E_AGENTS`. GUI tests open real windows on the desktop, so run them only when the user expects that.
- Packaging: `npm run dist` freezes the CLI and builds an unsigned NSIS installer; node-pty's N-API prebuilds are used as is (`npmRebuild: false`); the plugin files go to `resources/plugin`.
- Frame sampling: candidates less than 1 s apart are merged; a video without scene changes no longer reports scene detection as failed (FFmpeg 7 and 9 word an empty selection differently from older versions); reprocessing keeps the original transcript source in the manifest.
- README (Chinese) with screenshots in `docs/images/`, made by `npm run screenshots` from NASA's public-domain video GSFC_20181108_FERMI_m13042_Luck4K and its official captions (both fetched from images.nasa.gov), with an AI-output disclaimer as NASA's media guidelines ask. To rebuild them: download the `~medium.mp4` and `.srt` from images.nasa.gov into a neutral folder under one name, `process`, `summarize` with a Chinese request, `frame` one extra time, then run the script.
- Machine-specific paths removed from published files; `notes/` is local and ignored.
- Published on 2026-10-27 at the user's request: https://github.com/edsfod/video-agent, tag `v0.1.0` (CI passed on GitHub for both jobs), release with the unsigned installer (SHA256 `4d8f959eeafc0e89f73cedaecc18f148c6d51280bb70e63c62ec8139b4d3a550`). Checked after publishing: `uvx --from git+https://github.com/edsfod/video-agent@v0.1.0 video-agent --help` works, the release download matches the local hash, and `claude plugin marketplace add` plus `claude plugin install video-agent@video-agent` succeed in a temporary config directory. The first CI run caught `--help` crashing on a cp1252 pipe; output to pipes is now UTF-8.
- Published 0.1.1 on 2026-10-27 at the user's request: tag `v0.1.1` (CI passed on GitHub for all three jobs, run 40470241094), release with the installer built by CI (SHA256 `ee8ee12ab9466a7dd566be3a1f4844afb7ca4aaabbf3c960deeed825690ae312`) and the wheel (SHA256 `e3bf7d876f9801c133c3110a02bfec426b820cb844a70aecf5d49bad4524dce2`). Checked after publishing, with git and the system FFmpeg hidden from `PATH`: both downloads match the local hashes, the README's `uv tool install` and the skill's `uvx` command work from the release wheel, and a silent install and uninstall of the CI installer left `PATH` byte-identical and removed both shortcuts. CI caught two faults before release: PyInstaller left out the editable package in a fresh environment, and the GUI added a second `PATH` key beside Windows' `Path`, so the embedded terminal did not see the bundled CLI.

Open:

- Check the Codex route after 2026-11-25.
- Representative frames can include black frames (fade-ins); detecting them needs image analysis.
- Add site-specific authentication only if needed; `download` already accepts an explicit yt-dlp config file.
