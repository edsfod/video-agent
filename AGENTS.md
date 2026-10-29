# Project instructions

Rules for working on this project. Why each exists, and when it was decided, is in `docs/decisions/` and the git history; keep that out of this file.

## Product

- Keep platform-specific logic out (Yanhekt belongs to AutoSlides). Call AutoSlides Extractor and yt-dlp through their command lines; do not copy their code.
- `process` takes any local video path and never downloads; `download` is separate and optional. yt-dlp is the downloader; Media Downloader is not a backend.
- Subtitles come first: existing tracks or files beside the video, then a replaceable speech recogniser. Audio goes to a remote recogniser only with `--allow-remote-asr`.
- Representative frames follow the video: enough for every distinct page and scene, no fixed small count; a high limit only stops runaway output and says when reached. Codec keyframes and scene changes are not assumed meaningful.
- Detect the layout first; with a camera beside or inside the screen, look for page changes in the screen region only, at the source resolution.
- Slide extraction with AutoSlides Extractor is off unless `--extract-slides`, with explicit settings, behind a replaceable adapter.
- Never modify or move source videos, except `compress` replacing one with its checked smaller copy: this program's downloads by default, the user's own files only with their consent. Artifacts go to the workspace.
- The GUI and any other front end call the CLI; no media or summary logic of their own.
- yt-dlp and FFmpeg are Python dependencies; the installer bundles yt-dlp and its own LGPL FFmpeg (with its source on each release). Copies on `PATH` come first. Do not install other tools; say which is missing and how to point to it.

## Working

- Before pushing, run the tests the change touches on this machine (`.git/hooks/pre-push`: CLI tests, and the GUI tests with their windows off the screen); when they pass, push to `main`. GitHub's test runs follow without being waited for; fix what they find next. Installer tests (install, PATH, update) run only on GitHub, for packaging changes.
- Tag or release only when the user says. Set the version with `uv run scripts/bump_version.py <version>` and write `docs/releases/v<version>.md` by hand; releases are built on GitHub.
- Commit messages carry no AI attribution trailer.
- Record user-visible product decisions in `docs/decisions/` under their topic, marking those Claude made as `Claude judgment`; keep `ARCHITECTURE.md` describing the code as it is, and record each release's checks in `docs/release-log.md`. Research notes go in `notes/` (not published).
