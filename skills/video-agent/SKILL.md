---
name: video-agent
description: Summarize any video from a local file or a link with the Video Agent CLI - it prepares the transcript and pictures; you look at them and write a timestamped summary. Use for requests to summarize, take notes on, or answer questions about a video, lecture recording, talk, tutorial or news clip, given as a file path or a URL.
allowed-tools: Bash(video-agent *), Bash(uvx --from https://github.com/edsfod/video-agent/releases/download/v1.2.4/video_agent-1.2.4-py3-none-any.whl video-agent *)
---

# Video Agent

`<video-agent>` is `video-agent` when it is on `PATH`, otherwise `uvx --from https://github.com/edsfod/video-agent/releases/download/v1.2.4/video_agent-1.2.4-py3-none-any.whl video-agent` (needs uv: `winget install astral-sh.uv`, or install the desktop app from https://github.com/edsfod/video-agent/releases). Run each command on its own, paths quoted, without `cd`, `&&` or pipes. When a command fails or asks for something, tell the user what it said; do not call FFmpeg, yt-dlp or BCut yourself. `<video-agent> <command> --help` explains each command.

## A video

1. For a link, `<video-agent> download "<URL>" -o <folder>` prints the file.
2. `<video-agent> process "<video>" -o <workspace>` prints the video's folder.
3. Names or terms misheard more than once: `<video-agent> fix "<video>" --replace <wrong> <right> -o <workspace>`.
4. Read `summary-context.md` in that folder and look at the pictures it lists. `<video-agent> frame "<video>" <time> -o <workspace>` takes another.
5. Write the summary by `<video-agent> template` as `总结.draft.md` in that folder, then save it with `<video-agent> summarize "<video>" -o <workspace> --import --source "<your name>"`.
6. Reply with the overview, the main points with timestamps, the path of `总结.md`, and what is marked `需确认`.

## A collection

Related videos (a course, a series) go into `<video-agent> collection` (see its `--help`). Summarize each video, then write `合集总结.draft.md` (or `学习提纲.draft.md`) in the collection's folder and save it with `<video-agent> summarize --collection "<name>" -o <workspace> --import --source "<your name>"` (`--guide` for the study guide). `collection show` lists the videos to skip as `maybe_empty` and those whose summary is newer than the overview as `overview_behind`.
