# Command-line guide

The complete command and option list is in [commands.md](commands.md). This page explains the workflow. Video Agent offers an optional `download` command; `process` accepts local video files only and never downloads or processes them automatically.

Install Video Agent as described in the [README](../README.md), then run:

```powershell
video-agent --help
```

## Optional download

`download` calls yt-dlp only when explicitly invoked. It saves files to a local directory and prints their final paths; it never launches `process` automatically. Pass a printed path to a separate `process` command. A video downloaded elsewhere can be passed directly to `process` without yt-dlp.

```powershell
video-agent download "https://example.com/video" --output "D:\Video-Downloads"
video-agent process "D:\Video-Downloads\downloaded-video.mp4"
```

The default format selector is `bv*+ba/b`. Playlist-only URLs are refused by default; add `--playlist` to download all playlist entries. A video URL that also contains a playlist uses only that video by default. Video Agent ignores yt-dlp configuration files by default; pass `--yt-dlp-config` to load one explicit file. If Media Downloader is installed, Video Agent also finds the yt-dlp it keeps under `%APPDATA%\media-downloader\bin`. See [commands.md](commands.md) for all downloader options.

## Inspect and process

Inspect media streams without writing outputs:

```powershell
video-agent inspect "D:\Videos\lecture.mp4"
```

Prepare evidence for a summary:

```powershell
video-agent process "D:\Videos\lecture.mp4" --output "D:\Video-Work"
```

When `--output` is omitted, Video Agent uses `video-agent-output` under the current directory. Multiple video file paths can be passed to one `process` command.

## Default processing pipeline

1. Inspect the video with ffprobe, or read the same facts from ffmpeg when ffprobe is missing.
2. Read a matching `.srt` or `.vtt` sidecar, or extract an embedded subtitle stream.
3. Sample frames at the requested interval (default 60 seconds) and at detected scene changes. Keep at most 36 representative frames by default.
4. Write a manifest and `summary-context.md`. When a subtitle source is available, also write `transcript.srt` and `transcript.txt`.

The scene detector finds visual-change candidates; the time-based samples also cover long static shots. The resulting frames are evidence, not a claim that each is semantically important.

The CLI prepares summary context but does not generate model-written prose yet. `summary-context.md` contains transcript text and Markdown references to local frame images for an Agent or later model adapter.

## Speech recognition and privacy

If a video has audio but no sidecar or embedded subtitles, Video Agent saves available frame evidence and reports that transcription is incomplete. It does not upload audio by default.

To use BCut, pass both flags:

```powershell
video-agent process "D:\Videos\lecture.mp4" --asr bcut --allow-remote-asr
```

This extracts audio and uploads it to Bilibili BCut. `--allow-remote-asr` is required for each command that may upload audio. If the video already has usable subtitles, it uses them and does not upload audio.

BCut hands out a plain-HTTP upload address on `jssz-boss.biliapi.net`. Video Agent uses the system proxy like other programs. If a proxy rule blocks that host, the upload fails after three retries (about 12 seconds) with `audio chunk 1: upload returned HTTP 502` and an empty response; allow the host in the proxy rules rather than retrying.

## Optional slide extraction

Where AutoSlides Extractor is installed it finds the screen pages (`--no-extract-slides` turns it off); Video Agent runs AutoSlides Extractor in JSON command-line mode and saves its output under `slide-extraction/<run-id>/`. It uses explicit SSIM, downsampling, pHash, and ML settings rather than inheriting saved GUI preferences. Its CLI saves slide images and `timeline.json`; it does not create an editable `.pptx` or PDF. PDF export is a separate workflow in AutoSlides Extractor's GUI.

```powershell
video-agent process "D:\Videos\lecture.mp4" `
  --extract-slides --slide-extractor "C:\Program Files (x86)\AutoSlides Extractor\AutoSlidesExtractor.exe"
```




