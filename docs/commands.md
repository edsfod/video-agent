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
| `--no-subs` | Off | Do not save the site's subtitle tracks beside the video (saved by default; danmaku and live chat never are). |
| `--cookies FILE` | None | Netscape cookies file passed to yt-dlp. Bilibili lists its subtitles, the AI ones included, only to a logged-in account. |
| `--json` | Off | Print one JSON object per saved file; progress goes to standard error. |
| `--collection NAME` | None | Add the saved files, in order, to this collection of `--workspace` (made if missing); for playlists and series. |
| `--workspace PATH` | `video-agent-output` | The workspace that holds `--collection`. |
| `--follow` | Off | With `--playlist` and `--collection`: remember the list, so `collection update` fetches its new videos later. |
| `--auto` | Off | With `--follow`: let the desktop app check the list on its own while it runs. |

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

`process` uses the subtitles saved beside the video; with several, human subtitles come first, Chinese before other languages, AI subtitles last. yt-dlp cannot read a browser's cookies while the browser is open, nor those newer Edge and Chrome encrypt, so the desktop app signs in through a window of its own and passes the cookies from there.

Share-tracking query parameters are dropped before downloading: Bilibili's `vd_source`, `spm_id_from`, `from_spmid` and `share_*` marks, YouTube's `si` and `feature`, and `utm_*`. Parameters that select content, such as `?p=2` for a multi-part video's part or `?t=90`, stay.

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
| `--screen-region X,Y,W,H` | Detected | The screen part of the frame, in pixels, when the detected layout is wrong (see `layout.jpg` in the run's frame folder). |
| `--json` | Off | Print one JSON object per video; progress goes to standard error. |
| `--extract-slides`, `--no-extract-slides` | On where AutoSlides Extractor is installed and the video has a screen region | Find the screen pages with AutoSlides Extractor: its slides, with the steps of one slide merged, stand for the screen pages. `--no-extract-slides` (or `AUTOSLIDES_EXTRACTOR=none`) uses this program's own page search; `--extract-slides` runs it also on a video read as a camera picture. |
| `--slide-extractor PATH` | Auto-detected | Executable path for AutoSlides Extractor. Search order: this option, `AUTOSLIDES_EXTRACTOR`, `SlidesExtractor` or `AutoSlidesExtractor` on `PATH`, then common Windows install folders. |
| `--asr {none,bcut}` | `none` | Speech-recognition provider used only when no sidecar or embedded subtitles are available. |
| `--allow-remote-asr` | Off | Explicitly permits sending extracted audio to Bilibili BCut. Valid only with `--asr bcut`. |
| `--force` | Off | Process again a video processed before. Without it, a video already processed with the same frame settings is used as it is (each run samples a new set of frames), unless this run asks for more: a transcript it lacks (`--asr`), slides, a screen region, a subtitle file or `--overwrite-transcript`. The desktop app always passes it. |
| `--overwrite-transcript` | Off | Re-acquire transcript data even when `transcript.srt` already exists. If refresh fails, the prior transcript is kept and the run is marked incomplete. |
| `--subtitles FILE` | None | Use this SRT or WebVTT file as the transcript, whatever its name; replaces an existing transcript. One video only. |
| `--slides FOLDER` | None | Take the slide images (PNG, JPEG) in this folder: AutoSlides' `timeline.json` gives their times, otherwise each takes the time of the screen page it looks like. A `screen_<name>` video takes the `slides_<name>` folder AutoSlides keeps beside it without this option. One video only. |

#### Layout check and still pictures

When a recording of five minutes or more with a camera gives fewer than two screen pages, `process` says the layout may have been read wrong, names `layout.jpg` (the screen region outlined in green) and suggests `--screen-region`; `summary-context.md` carries the same note as a "Layout check" line.

The layout is one of `screen` (the whole frame), `split` (a screen beside a camera picture, also when the speaker hides part of the border), `inset` (a camera picture inside the screen, with or without a border, blacked out when looking for pages), `projected` (a camera filming a projection or a monitor: pages are looked for in that screen, by this program's own search) and `camera`. In a video read as a camera picture only, the pictures held still on the whole frame for 2 seconds or more (a chart or a screenshot between stock footage) are its screen pages; so are they when a filmed screen gives fewer than two pages.

#### Subtitle and upload behavior

The CLI checks a same-name `.srt` or `.vtt` sidecar first, then embedded subtitle streams. If either provides usable timed text, it writes `transcript.srt` and `transcript.txt`; it does not upload audio.

If audio exists but there are no local subtitles, the default `--asr none` leaves transcription incomplete. To choose BCut and allow the upload, both flags are required:

```powershell
video-agent process "D:\Videos\lecture.mp4" --asr bcut --allow-remote-asr
```

This permission is per invocation. If the video has no audio and no subtitles, the CLI writes an empty transcript and can still prepare visual evidence.

#### Slide extraction behavior

Where AutoSlides Extractor is installed it finds the screen pages: Video Agent invokes it in JSON command-line mode on the screen region (cropped out first when a camera picture is beside or inside it), with explicit extraction settings and a fresh output directory for each run, and merges the steps of one slide it keeps (a slide that only adds to the one before joins it, keeping the first time and the fuller picture). Pages it keeps too many (a video playing on a slide) are left to whoever writes the summary to drop. When it is missing or fails, this program's own page search runs. The external CLI saves slide images and `timeline.json`; it does not create an editable `.pptx` or PDF in this integration. PDF export is a separate workflow in AutoSlides Extractor's GUI.

```powershell
video-agent process "D:\Videos\lecture.mp4" --extract-slides
```

The CLI searches `PATH`, `AUTOSLIDES_EXTRACTOR`, and standard Windows install locations. Specify an executable path if needed:

```powershell
video-agent process "D:\Videos\lecture.mp4" `
  --extract-slides --slide-extractor "C:\Program Files (x86)\AutoSlides Extractor\AutoSlidesExtractor.exe"
```

### `models`

```powershell
video-agent models [--provider anthropic|openai] [--base-url URL] [--json]
```

Lists the summarize provider's model IDs from its model list (`GET …/models`), which costs no tokens; the window fills the model API's 模型 drop-down from it. `summarize --effort low|medium|high` sets how hard the model thinks: `reasoning_effort` for OpenAI-compatible APIs, an extended-thinking budget for Anthropic's; it is not sent when not given.

### `compress`

```powershell
video-agent compress VIDEO... [--json] [--check]
```

Re-encodes each video in place with SVT-AV1 (CRF 40) at its source resolution; a picture that hardly moves (a screen recording) goes to 10 frames a second. Audio that is AAC at 96 kbps or less is copied, other audio becomes AAC at 64 kbps; subtitles and metadata are kept. The new file replaces the old one only when its duration matches within a second and it is smaller. Videos already in AV1, HEVC or VP9, and videos this command compressed before (a tag in the file), are left alone. Needs an FFmpeg with `libsvtav1`, as the desktop installer's has.

`--json` prints one JSON object per video, progress to standard error. `--check` compresses nothing and tells each video's state: `compressed`, `efficient` (already AV1, HEVC or VP9), `not-smaller` (tried before; the copy was larger) or `null` (worth compressing). The state is kept in `compression.json` beside the settings, keyed by path, size and modification time, so `show` reports it as `compression` and `collection list` gives each video's from that file without opening the videos.

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
                      [--request TEXT] [--template NAME] [--effort low|medium|high] [--max-images N]
                      [--max-extra-frames N] [--no-tools] [--make-current] [--import [FILE] [--source S] [--note N]]
video-agent summarize --collection NAME [--guide] [-o WORKSPACE] [...]
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
| `--template NAME` | The chosen one | The summary template to follow for this summary (see `template --list`). |
| `--effort low\|medium\|high` | Not sent | How hard the model thinks (see `models`). |
| `--make-current`, `--overwrite` | Off | Make the new text the current `总结.md`; the one it replaces is kept as a version. Without it, a new text beside an existing one is kept as a version (see `versions`). |
| `--collection NAME` | None | Instead of a video: write the collection's overview (`合集总结.md`) from its videos' summaries. |
| `--guide` | Off | With `--collection`: write the study guide (`学习提纲.md`) instead. |
| `--source TEXT` | `导入` | With `--import`: what wrote it, such as `网页 AI` or `Claude Code`, kept with the version. |
| `--note TEXT` | None | With `--import`: a note kept with the version, such as the model. |
| `--import [FILE]` | None | Save a summary written elsewhere instead of calling a model: a file, `-` for standard input, or with no value the draft beside the summary (`总结.draft.md` in the video's folder; `合集总结.draft.md` or `学习提纲.draft.md` in the collection's), which is removed once saved. |

A summary from a chat AI may end with two sections that the import takes out. `## 字幕改正` lists recurring mishearings (`错的写法 → 正确写法`), which go into the cleaned transcript. `## 画面调整` lists pictures the chat AI does not need (`不用：frames/…`), which the import drops from the set of pictures in use (see `pictures`), and spans in which it misses one (`补截：00:02:20–00:02:30 what should be visible`), in which the import takes up to four different candidates into `frames/extra/`, preferring pictures held on screen. An answer imported from a file or standard input is a chat AI's and goes through rounds (a draft imported by `--import` alone, an Agent's, does not). The import checks what a program can see: the sections of the template (`--template`, default the chosen one), the `画面调整` section (written as 无 when there is nothing to change), stretches of the transcript with speech that no part of 详细内容 covers by the time range in its heading, and times past the end of the video. From the second round on the chat AI is asked for a 复查: to go through the transcript against its draft for every point, reason, example, number, definition, condition and conclusion said, and to end with `## 复查`, listing what it added (`补上：`) and corrected (`改正：`), sections it leaves out (`删掉的节：`) and spans it leaves out (`不写的时间段：00:10:00–00:15:00 why`), which the checks then accept, and for each linked picture what it shows that the transcript does not (`画面：frames/… what`); a link whose line says 无 is taken out and its picture not offered again, and a linked picture with no line is named in the next round. After a first draft, a 复查 that added or corrected something, a check that found something, or pictures wanted, the import says why and that there is a next round; `pack VIDEO --follow-up` (alone, `--zip` or `--folder`) gives it: the 复查, the problems found, the candidates and the summary as saved, to rewrite. A 复查's additions and corrections count only when the draft differs from the one before (blank lines and spaces aside). Each later round's answer (one with a 复查) overwrites the round before, whether that became the current summary or a version beside it. The state between rounds is in `summary-review.json` and `picture-review.json` in the video's folder.

The API key comes from Windows Credential Manager (saved with `config --set-key`), else `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`. An OpenAI-compatible server that needs no key, such as Ollama, works without one. The summary and the frames are sent to the configured provider.

### `config`

Show or change the `summarize` settings. With no options it prints the current provider, model, base URL, where the key comes from, and the settings file (`%APPDATA%\video-agent\settings.json`). Keys are never written to that file.

```powershell
video-agent config --provider anthropic --set-key
video-agent config --provider openai --model qwen2.5vl:7b --base-url http://127.0.0.1:11434/v1
video-agent config --delete-key
```

`--provider` also makes that provider the default; `--json` prints the resulting settings as JSON. `--set-key` reads the key without echoing it (or one line from standard input when not run in a terminal); `--delete-key` removes it.

### `template`

```powershell
video-agent template [NAME] [--list | --use | --default | --edit | --copy NEW | --reset | --accept | --info]
```

Print the summary rules and Markdown template that the Agent skill, `summarize` and `pack` follow: the chosen template, or the one named. Several exist side by side: the built-in `标准` and `命题分析` (claims as numbered propositions tagged 事实, 观点, 推断 or 引用, with the video's line of argument), and any of the user's own in `%APPDATA%\video-agent\templates`. `summarize` and `pack` take `--template NAME` for one summary.

- `--list`: every template as JSON, the chosen one marked `current`.
- `--use`: choose the named template for every summary from now on.
- `--default`: print a built-in template as it ships, not the user's copy of it.
- `--edit`: make the user's copy of a built-in template (once) and print its path as JSON; updates never change it.
- `--copy NEW`: make a template of the user's own named `NEW` from the named one.
- `--reset`: delete the user's copy of a built-in template, or a template of the user's own.
- `--accept`, `--info`: mark a copy as up to date with the built-in's changes; print where it is and whether it is outdated.

### `tools`

```powershell
video-agent tools [--json]
```

Prints where the external programs it would use are: FFmpeg, ffprobe, yt-dlp and AutoSlides Extractor, each found as `process` and `download` search for it; `null` (or `none`) for one not found. Changes nothing.

### `show`

```powershell
video-agent show VIDEO [-o WORKSPACE]
```

Prints JSON about a video's processing folder without changing anything: its length, whether it is processed, the paths of its manifest, summary, context and transcripts, its corrections, extra frames, subtitle files found beside the video and compression state. The desktop app reads it.

### `versions`

```text
video-agent versions VIDEO [-o WORKSPACE] [--use FILE | --delete FILE | --note FILE TEXT | --keep SOURCE] [--json]
video-agent versions --collection NAME [--guide] [...]
```

A summary written again does not replace the current one unless asked (`--make-current`): the new text is kept as a version beside it, `总结 (<date time>).md`, with what wrote it and a note in `总结.versions.json`. With no option it lists the versions.

- `--use FILE`: make this version current; the current text becomes a version.
- `--delete FILE`: delete a version (never the current text).
- `--note FILE TEXT`: set a version's note (`FILE` may be `总结.md`).
- `--keep SOURCE`: keep a copy of the current text as a version before something rewrites the file.
- `--collection NAME`, `--guide`: the collection's overview or study guide instead of a video's summary.

Each version records the set of pictures it was written with (`pictures` in `--json`, see `pictures`).

### `pictures`

```text
video-agent pictures VIDEO [-o WORKSPACE] [--use SET] [--drop PATH... | --restore PATH...] [--from SET] [--json]
```

Which of a video's pictures a summary is given, as a tree of sets. Set `0` holds every picture processing took and the extra frames taken outside a chat AI's rounds; each other set comes from its parent by dropping and adding pictures. One set is in use: every route, pack and context is given it. A chat AI's round grows a new set from it (without the pictures its `画面调整` names as 不用 or its 复查 says show nothing and those it was sent but does not link, with every picture its draft links), so a cheap AI may sort the pictures and a better one write from what is left. The pictures stay files in the video's folder; a set only names them. Processing again starts a new tree. With no option it lists the sets, `*` marking the one in use.

- `--use SET`: give later summaries this set.
- `--drop PATH...`, `--restore PATH...`: a new set without, or with again, these pictures (paths as in `--json`, relative to the video's folder), made from the set in use or `--from SET`, and put in use.
- `--json`: each set with its pictures (`members`) and the video's others (`dropped`).

### `pack`

```text
video-agent pack VIDEO [-o WORKSPACE] [--request TEXT] [--template NAME] [--follow-up]
                 [--zip FILE | --folder PARENT [--max-files N]] [--max-images N]
video-agent pack --collection NAME [--guide] [...]
```

The summary prompt for a chat AI on the web, which cannot run commands: the rules, the template and the evidence, with the answer asked for in one Markdown code block. Alone it prints the prompt; `--zip FILE` writes `提示词.md` and the pictures into a zip, the frames keeping their relative paths, so the summary's links work once imported; `--folder PARENT` writes `提示词.md` and numbered pictures into a new folder, for chat AIs that take no zip and a limited number of files: with more than `--max-files` (default 50, the prompt included), screen pages go on contact sheets to fit. Every picture carries its number and time in its lower left corner. `--max-images` (default 40) caps the whole frames put in besides every screen page.

`--follow-up` gives the next round after an imported answer that needs one (see `summarize`): the 复查 of the summary as saved, what the checks found and the candidates taken for the pictures asked for, to rewrite. The answer goes back with `summarize --import`. The desktop app's 「DeepSeek 网页」 route runs these rounds itself in a DeepSeek window.

### `fix`

```powershell
video-agent fix VIDEO [-o WORKSPACE] [--replace WRONG RIGHT]... [--remove WRONG] [--reset] [--json]
```

Corrects recurring mishearings of names and terms. The original transcript stays; the corrected one is written as `transcript.clean.srt` and `.txt`, and every later summary uses it. A Latin word matches as a whole word only, Chinese as written, also inside longer words, so give only forms that are wrong wherever they occur. `--remove WRONG` takes one back, `--reset` removes them all with the cleaned transcript; with no option it lists them. `--json` prints the corrections and the changed lines.

```powershell
video-agent fix "D:\Videos\lecture.mp4" -o D:\Video-Work --replace 延和课堂 延河课堂 --replace react ReAct
```

### `collection`

Groups related videos (a course, a series, a playlist) for an overview and a study guide. A collection is a folder in the workspace; the videos' own folders and summaries stay where they are. Every subcommand takes `-o WORKSPACE`.

| Subcommand | Meaning |
|---|---|
| `create NAME [VIDEO...]` | Make a collection, optionally with videos. |
| `add NAME VIDEO... [--at N]` | Add videos at the end, or before the Nth. |
| `remove NAME VIDEO...` | Take videos out. |
| `show NAME` | Each video with its state: processed, summarized, length, share of speech, maybe empty, skipped. |
| `list` | The collections in the workspace. |
| `delete NAME` | Remove the collection's own folder. |
| `skip NAME VIDEO --reason TEXT` | Mark a video with next to no content as skipped, with the reason shown in the overview; an empty reason takes it back. |
| `terms NAME [--replace WRONG RIGHT] [--remove WRONG]` | Corrections shared by every video, applied to each one's cleaned transcript. |
| `follow NAME [URL] [--folder DIR] [--auto\|--no-auto]` | Remember the list the videos come from (new videos are saved in `<workspace>/下载` unless `--folder`), or only turn the desktop app's own checks on or off. |
| `unfollow NAME` | Forget the list; the videos stay. |
| `update NAME [--cookies FILE] [--no-subs] [--json] ...` | Download the followed list's new videos and add them at the end, in order; the ones already downloaded are listed in the collection's `downloaded.txt`. |

Once each video has a summary, `summarize --collection NAME` writes the overview (things to note, the videos at a glance, the main line) and `--guide` the study guide (key points, points by topic, self-test questions with answers).

```powershell
video-agent collection create "机器学习" D:\Videos\ml-01.mp4 D:\Videos\ml-02.mp4 -o D:\Video-Work
video-agent collection terms "机器学习" --replace 剃度下降 梯度下降 -o D:\Video-Work
video-agent summarize --collection "机器学习" -o D:\Video-Work
video-agent summarize --collection "机器学习" --guide -o D:\Video-Work
video-agent download "https://space.bilibili.com/.../lists/...?type=season" --playlist --follow -o D:\Videos --collection "连载" --workspace D:\Video-Work
video-agent collection update "连载" -o D:\Video-Work
```

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

The CLI has no `slides` subcommand and no GUI command. AutoSlides Extractor is used by `process` where it is installed (`--no-extract-slides` turns it off).




