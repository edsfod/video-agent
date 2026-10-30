# Product rules

What Video Agent is and is not. These hold for every change; why each exists, and when it was decided, is in [decisions/](decisions/README.md).

## Scope

- Keep platform-specific logic out (Yanhekt belongs to AutoSlides). Call AutoSlides Extractor and yt-dlp through their command lines; do not copy their code.
- Stay general: another tool's folder layout is supported only as a named convention plus a manual import, never built in.
- The GUI and any other front end call the CLI; they hold no media or summary logic of their own.

## Video and download

- `process` takes any local video path and never downloads; `download` is separate and optional. yt-dlp is the downloader; Media Downloader is not a backend.
- Never modify or move source videos, except `compress` replacing one with its checked smaller copy: this program's downloads by default, the user's own files only with their consent. Artifacts go to the workspace.

## Transcript

- Subtitles come first: existing tracks or files beside the video, then a replaceable speech recogniser. Audio goes to a remote recogniser only with `--allow-remote-asr`.

## Pictures

- Representative frames follow the video: enough for every distinct page and scene, no fixed small count; a high limit only stops runaway output and says when reached. Codec keyframes and scene changes are not assumed meaningful.
- Detect the layout first; with a camera beside or inside the screen, look for page changes in the screen region only, at the source resolution.
- Screen pages come from AutoSlides Extractor where it is installed (the screen region cropped for it, the steps of one slide merged after it), otherwise from this program's own page rules; `--no-extract-slides` or `AUTOSLIDES_EXTRACTOR=none` turns it off. Explicit settings, behind a replaceable adapter.

## Dependencies

- yt-dlp and FFmpeg are Python dependencies; the installer bundles yt-dlp and its own LGPL FFmpeg (with its source on each release). Copies on `PATH` come first.
- Do not install other tools; say which is missing and how to point to it. The one exception: the settings download AutoSlides Extractor's portable build from its author's releases when the user clicks for it.
