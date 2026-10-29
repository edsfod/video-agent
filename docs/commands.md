# Command reference

This page lists every command and option currently implemented by Video Agent. It is the authoritative reference for the CLI parser.

## Invocation

After installing Video Agent as described in the [README](../README.md):

```powershell
video-agent --help
video-agent <command> --help
```

From a source checkout, `uv run video-agent <command>` runs the same commands, and `python -m video_agent` works in the installed environment.

`-h` and `--help` are available at the root and for each subcommand; they print help and exit with status 0. There is no interactive shell.

## Commands

### `download`

Download one or more URLs supported by yt-dlp into a local directory. This command returns the saved path(s) and does not start `process`.

```text
video-agent download URL... [OPTIONS]
```

| Argument or option | Default | Meaning |
|---|---|---|
| `URL...` | Required | One or more URLs accepted by yt-dlp. |
| `-o`, `--output PATH` | `video-agent-downloads` under the current directory | Directory for completed files. |
| `--format SELECTOR` | `bv*+ba/b` | yt-dlp format selector: best video plus best audio when separate, otherwise the best combined format. |
| `--playlist` | Off | Allow playlist downloads. Without this option, Video Agent checks the URL first, refuses playlist-only URLs, and uses `--no-playlist` for a URL containing a specific video and playlist. |
| `--yt-dlp PATH` | Auto-detected | Executable path. Search order: this option, `YT_DLP_EXECUTABLE`, `yt-dlp`/`yt-dlp.exe` on `PATH`, the Media Downloader-managed executable in the user's AppData directory (Windows), then the yt-dlp installed with Video Agent. |
| `--yt-dlp-config PATH` | None | Load this explicit yt-dlp config file. Other yt-dlp configuration files are ignored. |

Without `--playlist`, the command makes a metadata-only URL check and refuses links that resolve to a playlist; this avoids downloading a large list by surprise. The command uses yt-dlp's `--print after_move:filepath` to capture the final path after merge/post-processing. Its normal progress is shown in the terminal. If a playlist is enabled, it prints one path per completed item. Any returned path can then be passed to `process` separately.

```powershell
video-agent download "https://example.com/video" --output "D:\Video-Downloads"
video-agent process "D:\Video-Downloads\downloaded-video.mp4"
```

To intentionally download a playlist, add `--playlist`. Each completed item prints a local path; pass the paths you want to process as separate arguments:

```powershell
video-agent download "https://example.com/playlist" --playlist --output "D:\Video-Downloads"
video-agent process "D:\Video-Downloads\video-one.mp4" "D:\Video-Downloads\video-two.mp4"
```

Downloading is optional. Video Agent installs yt-dlp as a dependency, and the desktop installer bundles it, so `download` works without a separate install. A yt-dlp on `PATH` or the one Media Downloader keeps under `%APPDATA%\media-downloader\bin` is preferred when present, since either may be newer. yt-dlp is told where Video Agent's FFmpeg is, so separate video and audio streams are merged. If no executable or module is available, `download` reports the missing tool and exits with status 1. The downloader only handles URLs supported by yt-dlp. A video saved by any other method can be passed directly to `process`.

Share-tracking query parameters are not needed. For Bilibili, the bare `https://www.bilibili.com/video/<BV id>/` link is enough: on 2026-10-26, `BV1aknV6CEFB` downloaded successfully with its `?vd_source=...` suffix removed. Keep other query parameters (such as `?p=2` for a multi-part video's part) when they select specific content.

### `inspect`

Read one local video with ffprobe and print JSON containing its resolved path, duration in seconds, and stream records. It writes no output files.

```powershell
video-agent inspect "D:\Videos\lecture.mp4"
```

| Argument | Required | Meaning |
|---|---:|---|
| `VIDEO` | Yes | Path to a local video file; directories are not accepted. |

### `process`

Prepare transcript and visual evidence for one or more local videos. It does not download media or generate model-written prose.

```powershell
video-agent process VIDEO... [OPTIONS]
```

| Argument or option | Default | Meaning |
|---|---|---|
| `VIDEO...` | Required | One or more local video file paths; directories are not accepted. |
| `-o`, `--output PATH` | `video-agent-output` under the current directory | Root directory for per-video workspaces. |
| `--frame-interval SECONDS` | `60` | Positive number of seconds between regular frame samples. |
| `--scene-threshold VALUE` | `0.35` | FFmpeg scene-change threshold, greater than 0 and at most 1. |
| `--max-frames N` | `36` | Positive maximum number of representative frames written per video. |
| `--extract-slides` | Off | Run the local AutoSlides Extractor CLI and save slide images plus its timeline. |
| `--slide-extractor PATH` | Auto-detected | Executable path for AutoSlides Extractor. Search order: this option, `AUTOSLIDES_EXTRACTOR`, `SlidesExtractor` or `AutoSlidesExtractor` on `PATH`, then common Windows install folders. |
| `--asr {none,bcut}` | `none` | Speech-recognition provider used only when no sidecar or embedded subtitles are available. |
| `--allow-remote-asr` | Off | Explicitly permits sending extracted audio to Bilibili BCut. Valid only with `--asr bcut`. |
| `--overwrite-transcript` | Off | Re-acquire transcript data even when `transcript.srt` already exists. If refresh fails, the prior transcript is kept and the run is marked incomplete. |
| `--subtitles FILE` | None | Use this SRT or WebVTT file as the transcript, whatever its name; replaces an existing transcript. One video only. |
| `--slides FOLDER` | None | Take the slide images (PNG, JPEG) in this folder: AutoSlides' `timeline.json` gives their times, otherwise each takes the time of the screen page it looks like. A `screen_<name>` video takes the `slides_<name>` folder AutoSlides keeps beside it without this option. One video only. |

#### Subtitle and upload behavior

The CLI checks a same-name `.srt` or `.vtt` sidecar first, then embedded subtitle streams. If either provides usable timed text, it writes `transcript.srt` and `transcript.txt`; it does not upload audio.

If audio exists but there are no local subtitles, the default `--asr none` leaves transcription incomplete. To choose BCut and allow the upload, both flags are required:

```powershell
video-agent process "D:\Videos\lecture.mp4" --asr bcut --allow-remote-asr
```

This permission is per invocation. If the video has no audio and no subtitles, the CLI writes an empty transcript and can still prepare visual evidence.

#### Slide extraction behavior

Slide extraction is not part of the default run. `--extract-slides` invokes AutoSlides Extractor in JSON command-line mode, using explicit extraction settings and a fresh output directory for each run. The external CLI saves slide images and `timeline.json`; it does not create an editable `.pptx` or PDF in this integration. PDF export is a separate workflow in AutoSlides Extractor's GUI.

```powershell
video-agent process "D:\Videos\lecture.mp4" --extract-slides
```

The CLI searches `PATH`, `AUTOSLIDES_EXTRACTOR`, and standard Windows install locations. Specify an executable path if needed:

```powershell
video-agent process "D:\Videos\lecture.mp4" `
  --extract-slides --slide-extractor "C:\Program Files (x86)\AutoSlides Extractor\AutoSlidesExtractor.exe"
```

### `compress`

```powershell
video-agent compress VIDEO... [--json] [--check]
```

Re-encodes each video in place with SVT-AV1 (CRF 40) at its source resolution; a picture that hardly moves (a screen recording) goes to 10 frames a second. Audio that is AAC at 96 kbps or less is copied, other audio becomes AAC at 64 kbps; subtitles and metadata are kept. The new file replaces the old one only when its duration matches within a second and it is smaller. Videos already in AV1, HEVC or VP9, and videos this command compressed before (a tag in the file), are left alone. Needs an FFmpeg with `libsvtav1`, as the desktop installer's has.

`--check` compresses nothing and tells each video's state: `compressed`, `efficient` (already AV1, HEVC or VP9), `not-smaller` (tried before; the copy was larger) or `null` (worth compressing). The state is kept in `compression.json` beside the settings, keyed by path, size and modification time, so `show` reports it as `compression` and `collection list` gives each video's from that file without opening the videos.

### `frame`

Save single frames at chosen times into the video's processing workspace, for a closer look at a chart, slide or on-screen text that the representative frames missed. It writes JPEG files at 1280 pixels wide and prints each path.

```text
video-agent frame VIDEO TIME... [-o WORKSPACE]
```

| Argument or option | Default | Meaning |
|---|---|---|
| `VIDEO` | Required | Local video file. |
| `TIME...` | Required | One or more times as seconds (`70`), `MM:SS` (`1:10`) or `HH:MM:SS` (`00:01:10`). |
| `-o`, `--output PATH` | `video-agent-output` under the current directory | The workspace passed to `process` for this video. Frames go to `<workspace>/<video folder>/frames/extra/frame-HH-MM-SS.jpg`; an existing frame at the same second is replaced. |

A time at or beyond the end of the video is reported and skipped; the command then exits with status 1.

```powershell
video-agent frame "D:\Videos\lecture.mp4" 1:10 00:41:20 --output "D:\Video-Work"
```

### `summarize`

Optional. Write `总结.md` for a processed video with a model API, as an alternative to the Agent skill. Run `process` with the same `--output` first. The model receives `summary-context.md` and the representative frames plus any in `frames/extra/`, and follows the rules and template that `template` prints. When tool calling is on, the model can ask for more frames: `summarize` saves each into `frames/extra/` and sends the image back, up to `--max-extra-frames`.

```text
video-agent summarize VIDEO [-o WORKSPACE] [--provider anthropic|openai] [--model NAME] [--base-url URL]
                      [--request TEXT] [--max-images N] [--max-extra-frames N] [--no-tools] [--overwrite]
```

| Option | Default | Meaning |
|---|---|---|
| `-o`, `--output PATH` | `video-agent-output` | The workspace passed to `process`. |
| `--provider` | Set with `config` (initially `anthropic`) | `anthropic` uses the Messages API; `openai` uses any OpenAI-compatible Chat Completions API. |
| `--model NAME` | Set with `config`; `claude-sonnet-5-5` for Anthropic | Must accept images. `openai` has no default model. |
| `--base-url URL` | Set with `config`, else the provider's official URL | For example `http://127.0.0.1:11434/v1` for Ollama. |
| `--request TEXT` | None | The user's wishes, such as depth or focus, passed to the model. |
| `--max-images N` | 40 | Frames sent with the first request; more are thinned evenly. |
| `--max-extra-frames N` | 8 | Frames the model may request through tool calling; `0` allows none. |
| `--no-tools` | Off | Send no tool definition, for models without tool calling. |
| `--overwrite` | Off | Replace an existing `总结.md`. |

The API key comes from Windows Credential Manager (saved with `config --set-key`), else `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`. An OpenAI-compatible server that needs no key, such as Ollama, works without one. The summary and the frames are sent to the configured provider.

### `config`

Show or change the `summarize` settings. With no options it prints the current provider, model, base URL, where the key comes from, and the settings file (`%APPDATA%\video-agent\settings.json`). Keys are never written to that file.

```powershell
video-agent config --provider anthropic --set-key
video-agent config --provider openai --model qwen2.5vl:7b --base-url http://127.0.0.1:11434/v1
video-agent config --delete-key
```

`--provider` also makes that provider the default. `--set-key` reads the key without echoing it (or one line from standard input when not run in a terminal); `--delete-key` removes it.

### `template`

Print the summary rules and Markdown template shared by the Agent skill and `summarize`.

## Output layout

```text
<output>/<video-name>-<path-hash>/
  manifest.json
  transcript.srt
  transcript.txt
  summary-context.md
  frames/<run-id>/frame-*.jpg
  frames/extra/frame-HH-MM-SS.jpg
  总结.md
  slide-extraction/<run-id>/slides_<video-name>/
    slide_*.jpg
    timeline.json
```

Transcript files are created when a usable subtitle source is acquired. A silent video with no subtitles gets empty transcript files; a video with speech but no transcript provider leaves them absent and marks the run incomplete. The `summary-context.md` file contains transcript text and relative image references for representative frames and extracted slides. It is evidence for the Agent skill in `skills/video-agent/` or for the optional `summarize` command; either writes `总结.md` beside it. The source video is not moved or modified. Earlier frame and slide runs are retained.

## Exit status

- `0`: command completed; a silent video with no subtitles can complete with visual evidence only.
- `1`: a `download` URL failed, a `frame` time was beyond the end of the video, or at least one `process` input failed or has missing transcript/slide output. Any already-created partial evidence remains available.
- `2`: invalid arguments, an error before per-video processing (including an `inspect` failure), or a `summarize` or `config` failure such as a missing key or an API error.
- `130`: interrupted with Ctrl+C.

## Commands not implemented

The current CLI has `download`, `inspect`, `process`, and `frame`. It also has `summarize`, `config` and `template`. It has no `slides` subcommand and no GUI command. Slide extraction is the opt-in `process --extract-slides` option.




