# Scope: platform, product boundary, parts

The first decisions, 2026-10-26 and 2026-10-27. "Parts" is the plan as first written: since 2026-10-27 the CLI also calls model APIs (`summarize`, see [GUI](gui.md)). The parts as they are now are in [ARCHITECTURE.md](../../ARCHITECTURE.md).

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
5. **Representative frames** provide visual evidence independently of slide extraction. The sampler combines regular intervals with scene-change candidates, removes exact duplicate images, and records timestamps; since 2026-10-27 it keeps as many as the video has, up to a runaway limit of 500 (see [Layout and screen pages](layout-and-screen-pages.md)). Screen pages, one per distinct page of the screen region, come with them on every run. **Added:** it covers silent and visually dense videos; scene changes are candidates, not semantic judgments.
6. **Optional slide extraction** is a separate adapter to AutoSlides Extractor. The CLI invokes its local command-line mode only when the user passes `--extract-slides`; default is off. It writes slide images and a timeline map in a separate output directory. Representative-frame sampling remains independent.
7. **Evidence and summarization** writes `summary-context.md` with timed transcript text and image references. The CLI does not call a language model. The Agent skill `skills/video-agent/` writes `总结.md` from this evidence, adapted from the upstream yanhe-agent skill: the generic template replaces the lecture template, which remains a variant for lecture recordings. `frame` saves extra frames at times the Agent chooses. **Claude judgment:** a skill rather than a model API in the CLI keeps the core free of model-provider dependencies.
8. **Artifacts and jobs** store results in a workspace associated with the selected video. Source videos remain untouched. **Added:** the same artifacts can be consumed by the CLI now and a GUI later.

## Interface sequence — user decision

Build the CLI first and write the operating documentation. On 2026-10-27 the user brought the GUI back into scope (it had been deferred on 2026-10-26); see [GUI](gui.md). The CLI means text commands typed in PowerShell or another terminal; it is the first implementation interface, not a requirement that the project remain command-line-only. A GUI will select local files, show the default-off slide option, report progress, and open results by calling the same processing modules.

The current CLI also serves batch processing and future Agent integration. Do not put media processing logic in the GUI or an Agent skill. Do not add a resident MCP server in this phase.

```text
video-agent download <URL>... [download options]
video-agent inspect <local-video-path>
video-agent process <local-video-path>... [--extract-slides]
video-agent frame <local-video-path> <time>... [-o <workspace>]
```

`download` prints the resulting local file paths. `process` is a separate command; it obtains local or explicitly requested remote transcript data, samples representative frames, and writes an evidence bundle. `--extract-slides` opts into AutoSlides Extractor. The source video remains in place.

## First implementation boundary

Keep the generic core free of Yanhekt, BIT SSO, and course identifiers. Keep yt-dlp and AutoSlides Extractor behind replaceable executable adapters, not platform-specific processing logic. AutoSlides Extractor is not bundled; yt-dlp and FFmpeg are, since 0.1.1 (see [Distribution](distribution.md)). No GUI dependency belongs in the CLI core, and the core runs without any model provider; `summarize` loads a provider only when it is invoked.
