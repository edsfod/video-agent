---
name: video-agent
description: Summarize any video from a local file or a link - prepare its transcript (existing subtitles first, BCut speech recognition only with the user's consent) and representative frames with the Video Agent CLI, look at the frames, and write a timestamped summary. Use for requests to summarize, take notes on, or answer questions about a video, lecture recording, talk, tutorial or news clip, given as a file path or a URL.
allowed-tools: Bash(video-agent *), Bash(uvx --from git+https://github.com/edsfod/video-agent@v0.1.0 video-agent *)
---

# Video Agent

## Running commands

`<video-agent>` stands for `video-agent` when that command is on `PATH` (installed with `uv tool install`), and otherwise for `uvx --from git+https://github.com/edsfod/video-agent@v0.1.0 video-agent`, which fetches this skill's matching version of the CLI on first use. Check once with `video-agent --help`. If neither works because `uv` is missing, tell the user to install uv (`winget install astral-sh.uv`) and FFmpeg (`winget install Gyan.FFmpeg`). Run each command as a single `<video-agent> …` with the paths written out and no `cd`, variables, `&&` or pipes, so a harness can approve the prefix once. Quote paths that contain spaces or brackets.

When a command fails, tell the user what it said instead of working around it: do not call FFmpeg, yt-dlp or BCut yourself and do not edit the CLI. The full command reference is `docs/commands.md` in the repository.

## Before you start

- **Source videos stay where they are.** The CLI writes everything into a workspace, by default `video-agent-output` in the current folder; pass `-o <folder>` to every command for one video when the user names another place, and use the same workspace for `process` and `frame`.
- **Speech recognition uploads audio.** When a video has no subtitle track and no `.srt`/`.vtt` file of the same name, `process` stops short of a transcript and says so. BCut, Bilibili's speech recognition, can transcribe it, but it receives the video's audio. Explain that and run `process … --asr bcut --allow-remote-asr` only after the user agrees in this conversation; never agree for them. A user who agreed once for a request has agreed for the videos of that request.
- **Slide extraction is off by default.** Add `--extract-slides` only when the user asks for the slides or a slide deck; it runs AutoSlides Extractor and takes much longer.

## Summarize a video

1. **Get a local file.** A local path is used as it is. For a link, run `<video-agent> download "<URL>" -o <folder>` and take the path it prints. Drop share-tracking query parameters such as `?vd_source=…` and `?spm_id_from=…`, but keep ones that pick the content, such as `?p=2`. For a playlist or collection, ask which videos are wanted before adding `--playlist`.
2. **Prepare the evidence.** Run `<video-agent> process "<video>" [more videos] -o <workspace>`. Each video gets its own folder in the workspace (the command prints it), holding `summary-context.md`, `transcript.srt`, `transcript.txt`, `frames/` and `manifest.json`. If the transcript is missing, ask about BCut as above and run `process` again with the two flags. Run `process` once per video in a conversation; later questions and rewrites reuse its folder, since each run samples a new set of frames.
3. **Read the evidence.** Read `summary-context.md`: the timed transcript, then the representative frames it lists. Look at the frames, not just their names: they show slides, charts, code, burned-in subtitles and on-screen text that the speech leaves out. Where the speaker points at the screen ("我们看看这个数据", "如图", "this table") or the transcript is unclear and no frame is near, run `<video-agent> frame "<video>" <time>... -o <workspace>` and look at what it saves in `frames/extra/`.
4. **Write the summary** as `总结.md` in that video's folder. Run `<video-agent> template` once and follow the rules and template it prints; the `summarize` command uses the same text, so every route writes the same kind of summary. For several related videos, also write `合集总结.md` in the workspace.
5. **Reply** with the short overview, the main points with timestamps, and the path of `总结.md`. Mention anything marked `需确认`.

To answer a question about a video that is already processed, read its `总结.md` first, then `transcript.txt` and the frames, and cite timestamps.
