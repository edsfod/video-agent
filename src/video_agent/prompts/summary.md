# Writing a video summary

This file is shared by the Agent skill and the `summarize` command, so every route writes the same kind of summary. Print it with `video-agent template`.

## Rules

- **Cover the content, not only its outline.** 详细内容 is the body of the summary: go through the video part by part and keep what a viewer would want to note down, such as claims and the reasons given for them, figures, examples, steps, and what is shown on screen when it adds to what is said. Its length follows how much the video says, not a fixed size; leave out repetition, filler and small talk, and shorten only when the user asks. Write in the language of the user's request, or of the video when there is no request.
- **Use the pictures where they carry information.** Screen pages and frames show text, tables, charts and objects that the speech refers to or leaves out. Work what they add into the summary where it matters and link the picture; there is no need to mention every one.
- **Only what the evidence backs.** Every point comes from the transcript, a frame or a slide and carries its timestamp; link frames that support a point. Do not add outside knowledge to the summary. Mark anything doubtful `需确认` with its timestamp instead of guessing.
- **Claims belong to the speaker.** Write figures, news and opinions as what the video says ("视频称……", "作者认为……"), not as established fact, and keep the speaker's hedges. Check them against other sources only when the user asks, in a separate section.
- **Correct the transcript in your head, not in the file.** BCut turns names and terms into homophones. Take the right form from the frames (titles, slides, burned-in subtitles) or from context and use it in the summary; do not edit `transcript.srt` line by line. When the right form is uncertain, mark it `需确认`.
- **One current version.** Rewrite `总结.md` in place when asked for changes; do not append update sections or save copies.

## 总结模板

每个视频一篇 `<视频文件夹>/总结.md`，写在 `process` 为它建的文件夹里，和 `summary-context.md` 放在一起。几个相关视频（一个合集、一门课的几讲）另写一篇 `<工作区>/合集总结.md`。模板定下标题和顺序；内容默认写透，用户要短时再压缩。

写法：

- 只链接确实存在的文件。视频文件夹里的文件用相对路径，如 `[字幕](transcript.txt)`、`[画面](frames/extra/frame-00-01-10.jpg)`；源视频用绝对路径，斜杠用 `/`；路径里有空格或方括号时写成 `[名字](<路径>)`，名字里的方括号写成 `\[`、`\]`。源视频写成普通文字的视频名加一个 `[打开视频](<路径>)` 链接：视频名是文件名去掉扩展名，再把下载工具为文件名替换的 `⧸`、`⧹` 换回 `/`、`\`，方括号照原样写，不用转义。
- 时间点统一写成 `HH:MM:SS`，放在反引号里。
- 某一节确实没有内容就删掉这一节，「需确认」除外：没有就写 `无`。

## 视频总结 `总结.md`

```markdown
# <视频标题>

视频：<视频名> · [打开视频](<源视频的绝对路径>) · 时长：<M:SS，一小时以上写 H:MM:SS> · 字幕：[transcript.txt](transcript.txt)（<来源：BCut 转录 / 内嵌字幕 / 字幕文件>）

## 概要

两到四句话：视频讲什么、主要结论或观点是什么、作者是谁或站在什么立场（视频里看得出来时）。

## 要点

- 一句话一个要点，按重要性排，附 `00:01:10` 和需要时的 [画面](frames/...)

## 时间线

| 时间 | 内容 | 出处 |
| --- | --- | --- |
| `00:00:00` | 一句话说清这一段讲什么、为什么值得回看 | |
| `00:01:10` | 展示的图表或画面上的关键信息 | [画面](frames/extra/frame-00-01-10.jpg) |

## 详细内容

按视频自己的结构分段，每段一个小标题，标出时间范围（如 `00:12:30`–`00:25:10`）：这一段讲了什么、理由和依据、数据和例子、画面上补充的内容，附时间点，需要时链接画面。写到没看视频的人也能明白这一段的程度。

## 需留意

视频里明确提到、观众容易漏掉的事项：截止时间、要做的事、警告、链接或资源。没有就删掉这一节。

## 需确认

- `00:03:20` 字幕听不清、前后矛盾或专有名词拿不准的地方
```

**课堂录像**在「概要」后加一节，内容取自上游延河课堂的课次笔记：

```markdown
## 要点速查

- 点名、签到、小测：
- 作业和截止时间：
- 考试和复习提示：
- 通知和其他提醒：
```

没有的项写 `无`。

## 合集总结 `合集总结.md`

```markdown
# <合集名>

## 各视频一览

| 视频 | 时长 | 总结 | 一句话 |
| --- | --- | --- | --- |
| <标题> | <MM:SS> | [总结](<视频文件夹>/总结.md) | 一句话，句末不加句号 |

## 主线

按主题而不是按视频顺序串起各个视频：每个主题一段，指向讲它的视频总结和时间点。

## 需确认

- 各视频之间矛盾的说法，附各自的视频和时间点
```

每写完或改完一篇视频总结，就把它并进合集总结：一览里的那一行、主线里相关的主题。
