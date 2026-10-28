# Writing a video summary

This file is shared by the Agent skill and the `summarize` command, so every route writes the same kind of summary. Print it with `video-agent template`.

## Rules

- **Cover the content, not only its outline.** 详细内容 is the body of the summary: go through the video part by part and keep what a viewer would want to note down, such as claims and the reasons given for them, figures, examples, steps, and what is shown on screen when it adds to what is said. Its length follows how much the video says, not a fixed size; leave out repetition, filler and small talk, and shorten only when the user asks. Write notes a reader can scan, not the talk retold sentence by sentence in its order. Judge for each part which form its content suits, such as a few sentences, a list, a table or numbered steps, rather than giving every part the same shape. Write in the language of the user's request, or of the video when there is no request.
- **Use the pictures where they carry information.** Screen pages and frames show text, tables, charts and objects that the speech refers to or leaves out. Work what they add into the summary where it matters and link the picture shown at that point of the video; there is no need to mention every one.
- **Keep what the video says apart from what you add.** Every point from the video comes from the transcript, a frame or a slide and carries its timestamp; link frames that support a point. You may add what helps the reader beyond the video (background, how something works, a definition, a known correction), but start each addition with `补充：` so it is never taken for the speaker's words, and never put words or pictures into the video that it does not have. Mark anything doubtful in the video `需确认` with its timestamp instead of guessing.
- **Claims belong to the speaker.** Write figures, news and opinions as what the video says ("视频称……", "作者认为……"), not as established fact, and keep the speaker's hedges and strength: what the speaker advises against stays advised against, not forbidden. Check them against other sources at length only when the user asks, in a separate section.
- **Clean the transcript of recurring mishearings; keep the original.** Speech recognition turns names and terms into homophones. Take the right form from the screen pages and frames (titles, slides, burned-in subtitles) or from context. A form that is wrong every time it occurs goes into the cleaned transcript (`video-agent fix`, which keeps `transcript.srt` as it was and writes `transcript.clean.*`, used from then on); a one-off mistake, or a form that is also a real word, is corrected only in the summary. When the right form is uncertain, mark it `需确认`.
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

几个相关的视频（一门课、一个系列、一个播放列表）组成一个合集，合集总结写在合集文件夹里（`<工作区>/合集/<合集名>/合集总结.md`），链接各集的总结用相对路径 `../../<视频文件夹>/总结.md`。先有各集的总结，再写合集总结。

```markdown
# <合集名>

## 需留意

- 各集提到的截止时间、要做的事、警告、通知和资源，按时间先后，附出处：[<视频名> `00:42:10`](../../<视频文件夹>/总结.md)

## 各集一览

| # | 视频 | 时长 | 总结 | 需留意 | 一句话 |
| --- | --- | --- | --- | --- | --- |
| 1 | <视频名> | <M:SS> | [总结](../../<视频文件夹>/总结.md) | ✅ | 一句话，句末不加句号 |

## 主线

按主题而不是按视频顺序串起各集：每个主题一段，指向讲它的视频总结和时间点。

## 跳过的视频

- <视频名>：跳过的原因（几乎没有讲话、只有几分钟、和其他集重复……）

## 需确认

- 各集之间矛盾的说法，附各自的视频和时间点
```

「需留意」那一列：这一集的总结里有「需留意」的内容就打 ✅。没有跳过的视频就删掉那一节。每写完或改完一集的总结，就把它并进合集总结：需留意、一览里的那一行、主线里相关的主题。

## 学习提纲 `学习提纲.md`

用户要复习、自学或准备考试时，在合集文件夹里写学习提纲。它根据各集的总结、字幕和画面写，不引入视频以外的内容；范围按用户的要求，默认是整个合集。

```markdown
# <合集名> 学习提纲

范围：<哪几集，或哪些主题>

## 重点

- 讲者强调过的内容：要掌握什么、会怎么考或怎么用、常见的错误，附 [<视频名> `00:42:10`](../../<视频文件夹>/总结.md)

## <主题>

- 概念、定义、公式或步骤：一句话说明，附时间点，需要时链接画面
- 例子：要点和思路

## 自测题

1. 题目

<details><summary>答案</summary>

答案，以及出自哪一集、哪个时间点

</details>
```

主题按合集的主线分，和合集总结保持一致；自测题覆盖每个主题，答案能在视频里找到出处。
