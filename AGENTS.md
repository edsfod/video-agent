# Project instructions

This project grew out of [edsfod/yanhe-agent](https://github.com/edsfod/yanhe-agent) and is developed separately; do not change that repository from here. AutoSlides Extractor and yt-dlp are optional external tools; invoke their documented CLIs instead of copying their implementations.

## Product rules

- Accept explicit local video paths without requiring a platform-specific course folder or filename.
- Keep downloading optional and separate from processing. The `download` command may create local files; the `process` command accepts local paths and never downloads implicitly.
- Use yt-dlp as the first optional downloader adapter. Do not use Media Downloader as a backend; it is a GUI frontend. A future project GUI must call the shared core.
- Keep subtitle acquisition a primary stage; use existing subtitle tracks or sidecar files where suitable, and keep ASR backends replaceable.
- Require an explicit `--allow-remote-asr` flag before sending audio to a remote recognition provider.
- When preparing a summary, extract a bounded set of timestamped representative frames independently of slide extraction.
- Keep slide extraction optional and disabled by default. Run AutoSlides Extractor only when the user passes `--extract-slides`.
- Pass explicit AutoSlides Extractor settings rather than inheriting saved GUI preferences; keep the external executable behind a replaceable adapter.
- Do not treat codec keyframes or scene-change candidates as guaranteed semantically important frames.
- Do not modify or move source videos. Write artifacts into a separate workspace.
- The GUI (Electron, per ARCHITECTURE.md) and any other front end call the CLI and must not duplicate media or summary logic.
- Do not tag, publish or create a release until the user says all planned work is finished.
- Do not install yt-dlp or other external tools automatically. Report the missing optional tool and its explicit path/configuration options.

## Design record

Record user-visible product decisions in `ARCHITECTURE.md`. Local research notes may live in `notes/`, which is not published. Mark agent-made design decisions as `Claude judgment` and explain what each decision changes.

