---
name: video-agent
description: Summarize any video from a local file or a link - prepare its transcript (existing subtitles first, BCut speech recognition only with the user's consent) and representative frames with the Video Agent CLI, look at the frames, and write a timestamped summary. Use for requests to summarize, take notes on, or answer questions about a video, lecture recording, talk, tutorial or news clip, given as a file path or a URL.
allowed-tools: Bash(video-agent *), Bash(uvx --from https://github.com/edsfod/video-agent/releases/download/v0.9.2/video_agent-0.9.2-py3-none-any.whl video-agent *)
---

# Video Agent

## Running commands

`<video-agent>` stands for `video-agent` when that command is on `PATH` (the desktop installer adds its bundled copy; `uv tool install` adds one too), and otherwise for `uvx --from https://github.com/edsfod/video-agent/releases/download/v0.9.2/video_agent-0.9.2-py3-none-any.whl video-agent`, which fetches this skill's matching version of the CLI on first use; it needs uv but not git, and brings its own FFmpeg and yt-dlp. Check once with `video-agent --help`. If neither works because `uv` is missing, tell the user to install the Video Agent desktop app from https://github.com/edsfod/video-agent/releases or uv (`winget install astral-sh.uv`), and to start a new session afterwards so the new `PATH` is seen. Run each command as a single `<video-agent> …` with the paths written out and no `cd`, variables, `&&` or pipes, so a harness can approve the prefix once. Quote paths that contain spaces or brackets.

When a command fails, tell the user what it said instead of working around it: do not call FFmpeg, yt-dlp or BCut yourself and do not edit the CLI. When it says another Video Agent run is changing the folder (perhaps the desktop app), tell the user and wait for it rather than retrying in a loop. The full command reference is `docs/commands.md` in the repository.

## Before you start

- **Source videos stay where they are.** The CLI writes everything into a workspace, by default `video-agent-output` in the current folder; pass `-o <folder>` to every command for one video when the user names another place.
- **Speech recognition uploads audio.** When a video has no subtitle track and no `.srt`/`.vtt` file of the same name, `process` stops short of a transcript and says so. BCut, Bilibili's speech recognition, can transcribe it, but it receives the video's audio. Explain that and run `process … --asr bcut --allow-remote-asr` only after the user agrees in this conversation; never agree for them. A user who agreed once for a request has agreed for the videos of that request.
- **Slide extraction is off by default.** Add `--extract-slides` only when the user asks for the slides or a slide deck; it runs AutoSlides Extractor and takes much longer.

## Summarize a video

1. **Get a local file.** A local path is used as it is. For a link, run `<video-agent> download "<URL>" -o <folder>` and take the path it prints. For a playlist or collection, ask which videos are wanted before adding `--playlist`.
2. **Prepare the evidence.** Run `<video-agent> process "<video>" [more videos] -o <workspace>`. Each video gets its own folder in the workspace (the command prints it), holding `summary-context.md`, `transcript.srt`, `transcript.txt`, `frames/` and `manifest.json`. A video processed before is used as it is, so running `process` again is safe. If the transcript is missing, ask about BCut as above and run `process` again with the two flags.
3. **Clean the transcript** when the same name or term is misheard more than once (the screen pages, titles and frames show the right form): run `<video-agent> fix "<video>" --replace <wrong> <right> [--replace <wrong> <right>]... -o <workspace>`. Give only forms that are wrong wherever they occur (`fix --help` says how they match); a form that is also a real word is corrected only in the summary. Check the lines it prints, take a wrong correction back with `--remove <wrong>`, and fix nothing when there is nothing recurring.
4. **Read the evidence.** Read `summary-context.md`: the timed transcript, marked with the screen page on screen at each point, the representative frames, the screen pages, and frames taken where the speaker points at something. Look at the pictures, not just their names: they show slides, charts, code, burned-in subtitles and on-screen text that the speech leaves out; in a lecture the screen pages carry most of the content. When the context has a "Layout check" line, tell the user. Where the transcript is unclear or refers to something you cannot see in any picture, run `<video-agent> frame "<video>" <time>... -o <workspace>` and look at what it saves in `frames/extra/`.
5. **Write the summary.** Run `<video-agent> template` once and follow the rules and template it prints: the summary template the user chose. Several can exist side by side (`<video-agent> template --list`); when the user or the task names one, run `<video-agent> template "<name>"` and follow that one instead. Write the summary as `总结.draft.md` in the video's folder (so its `frames/…` links resolve), then save it with `<video-agent> summarize "<video>" -o <workspace> --import --source "<your name, such as Claude Code>"`, which removes the draft. The first summary becomes `总结.md`; when there is one already, the new one is kept as a version beside it and the user chooses (add `--make-current` only when the user asked to replace the summary).
6. **Reply** with the short overview, the main points with timestamps, and the path of `总结.md`. Mention anything marked `需确认`.

## A collection

Several related videos (a course, a series, a playlist, a workshop) form a collection, with an overview (`合集总结.md`) and, when the user wants to study or revise, a study guide with self-test questions (`学习提纲.md`), both in `<workspace>/合集/<name>/`. Use one when the user names a series or a set of videos, or downloads a playlist (`<video-agent> download "<URL>" --playlist -o <folder> --collection "<name>" --workspace <workspace>` fills it in order; add `--follow` for a series that is still growing, and later `<video-agent> collection update "<name>" -o <workspace>` downloads only its new videos).

1. **Gather the videos**: `<video-agent> collection create "<name>" <videos>... -o <workspace>`, or `collection add` to an existing one; `collection show "<name>" -o <workspace>` prints each video's state as JSON.
2. **Process** them (`process` takes several at once).
3. **Leave out empty ones.** `show` marks videos that are very short or almost wordless as `maybe_empty`; look at their transcript and frames, and for one with nothing to summarize (a cancelled session, an empty room, a duplicate) run `collection skip "<name>" "<video>" --reason "<why>" -o <workspace>`. The reason appears in the overview.
4. **Shared terms.** A name or term misheard across the videos goes into `collection terms "<name>" --replace <wrong> <right> -o <workspace>`, which cleans every video's transcript, including videos processed later; the rules of step 3 above apply.
5. **Summarize each video** as above. For many videos, hand a few to each subagent (the cheapest that can see images and write files), giving it the workspace, its videos and the `<video-agent> template` command to follow (with the template's name when one was named), and asking for each `总结.md` and a report of its 需留意 items with timestamps.
6. **Write the overview** from the template, as `合集总结.draft.md` in the collection's folder (`学习提纲.draft.md` for the study guide), linking each video's summary as `../../<video folder>/总结.md`, and save it with `<video-agent> summarize --collection "<name>" -o <workspace> --import --source "<your name>"` (add `--guide` for the study guide); as for a summary, an existing text stays and the new one is kept as a version. `collection show` lists in `overview_behind` and `guide_behind` the videos whose summary changed after the overview or guide was written; bring those up to date.
7. **Reply** with the 需留意 items, the skipped videos and why, and the paths of the files.

To answer a question about a video that is already processed, read its `总结.md` first, then the transcript (`transcript.clean.txt` when there is one, else `transcript.txt`) and the frames, and cite timestamps.
