# Project instructions

This project grew out of [edsfod/yanhe-agent](https://github.com/edsfod/yanhe-agent) and is developed separately; do not change that repository from here. AutoSlides Extractor and yt-dlp are external tools; invoke their documented CLIs instead of copying their implementations.

## Product rules

- Accept explicit local video paths without requiring a platform-specific course folder or filename.
- Keep downloading optional and separate from processing. The `download` command may create local files; the `process` command accepts local paths and never downloads implicitly.
- Use yt-dlp as the first optional downloader adapter. Do not use Media Downloader as a backend; it is a GUI frontend. A future project GUI must call the shared core.
- Keep subtitle acquisition a primary stage; use existing subtitle tracks or sidecar files where suitable, and keep ASR backends replaceable.
- Require an explicit `--allow-remote-asr` flag before sending audio to a remote recognition provider.
- When preparing a summary, extract timestamped representative frames independently of slide extraction. Their number follows the video, enough to cover every distinct screen page (slides, code, documents) and scene; do not cut them to a fixed small count. A high limit only stops runaway output and is reported when reached (user decision, 2026-10-27).
- Detect the layout before looking for page changes: where a camera picture sits beside or inside the screen, look for changes in the screen region only, at the source resolution. Built-in layout detection and page detection run on every `process`.
- Keep slide extraction optional and disabled by default. Run AutoSlides Extractor only when the user passes `--extract-slides`.
- Pass explicit AutoSlides Extractor settings rather than inheriting saved GUI preferences; keep the external executable behind a replaceable adapter.
- Do not treat codec keyframes or scene-change candidates as guaranteed semantically important frames.
- Do not modify or move source videos. Write artifacts into a separate workspace.
- The GUI (Electron, per ARCHITECTURE.md) and any other front end call the CLI and must not duplicate media or summary logic.
- Do not tag, publish or create a release until the user says all planned work is finished.
- Push work to a branch (`dev/<topic>`) and fast-forward `main` only after CI passed on that branch, so `main` receives only commits that passed CI, including the GUI tests that run only there (user decision, 2026-10-28). Commit messages carry no AI attribution trailer.
- yt-dlp and FFmpeg (through `imageio-ffmpeg`) are Python dependencies; the desktop installer bundles yt-dlp and its own LGPL FFmpeg build instead of imageio-ffmpeg's GPL one, and offers that FFmpeg's source with each release (user decisions, 2026-10-27 and 2026-10-28; see ARCHITECTURE.md "Distribution" and "Bundled FFmpeg"). Copies on `PATH` are preferred. Do not install other external tools, such as AutoSlides Extractor, automatically. Report the missing optional tool and its explicit path/configuration options.

## Design record

Record user-visible product decisions in `ARCHITECTURE.md`. Local research notes may live in `notes/`, which is not published. Mark agent-made design decisions as `Claude judgment` and explain what each decision changes.

