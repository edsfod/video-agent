# Writing a video summary

This file is shared by the Agent skill and the `summarize` command, so every route writes the same kind of summary. Print it with `video-agent template`.

## Rules

- **Cover the content, not only its outline.** 详细内容 is the body of the summary: go through the video part by part and keep what a viewer would want to note down, such as claims and the reasons given for them, figures, examples, steps, and what is shown on screen when it adds to what is said. Its length follows how much the video says, not a fixed size; leave out repetition, filler and small talk, and shorten only when the user asks. Write notes a reader can scan, not the talk retold sentence by sentence in its order. Write in the language of the user's request, or of the video when there is no request.
- **Separate what is claimed from what is asked.** What can be true or false (claims, figures, reasons, conclusions) is written as numbered propositions in 详细内容. What cannot (attendance, quizzes, assignments and deadlines, assessment and grading, course requirements, instructions, notices, links and resources) is not a proposition and goes into 元信息. Examples, demonstrations, tables and steps go under the proposition they illustrate or serve; a procedure taught as such is written as numbered steps, and what is claimed about it (why it works, when to use it) as propositions.
- **Tag each proposition by its standing in the video, not by whether it is true.** Ask in this order and take the first tag that fits:
  1. `引用`: the speaker attributes it to someone else (a paper, a book, a person, an institution, "有研究表明"). Name the source as the video gives it, and the speaker's stance: 认同, 反对 or 只转述.
  2. `观点`: it says what is good, right, important, advisable or likely, or how something should be understood, rather than what is the case: an evaluation, a recommendation, a norm, an interpretation or a prediction.
  3. `推断`: it says what is the case, and the video derives it from other propositions; list them as `← P2, P5`.
  4. `事实`: it says what is the case, without a derivation in the video: an observation, data, an event, how something works, a definition (written as `定义：<术语>指……`).
  An `观点` the video argues for lists its premises too. A tag records how the speaker presents a claim; `事实` is not a verdict that the claim is true.
- **Show the reasoning.** Number the propositions `P1`, `P2`… through the whole summary in the order they first appear. Where the video argues, write what supports or attacks what (`← P3`, `反驳 P4`). A premise a step needs but the video does not state is added as a proposition tagged `补全`: the weakest premise that makes the step work, marked as your reconstruction. 论证结构 draws the video's main line, its main conclusions and what each rests on; everything else stays in 详细内容. Where the support is weaker than the conclusion (a general claim from a few examples, a correlation taken for a cause, a conclusion stronger than its premises), say so in a `补充：` line; do not otherwise judge whether the speaker is right.
- **Make each proposition exact.** Rewrite what is said as a well-defined proposition: name the subject and what it is about; state the quantifier (all, most, some, in which cases, how many) and the conditions (if, only if, unless); replace words that depend on the moment ("这个", "这里", "我们", "现在", "去年") with what they refer to; give the time and scope it holds for. Keep the speaker's strength: "一般" does not become "总是", nor "可能" become "会".
  - Take the reading that someone who knows the subject would take in context, and among such readings the one the speaker most likely meant. Do not change what was said to make it true.
  - When a statement has several such readings and they would make materially different propositions, list them as options that exclude each other and together cover every case, say which you take and why, and add it to 需确认 when the context does not decide. When it has no such reading (the transcript is garbled and no frame helps), give the nearest guess and add it to 需确认.
  - Where words easily blur the structure (nested conditions, the order of quantifiers, a necessary against a sufficient condition, a definition against a claim about the thing defined), add a formal version (logic, sets or a formula) followed by one sentence in plain language. Elsewhere write naturally.
- **The pictures are material, not illustrations.** Screen pages and frames show text, tables, charts, documents, formulas, code and objects that the speech refers to or leaves out. Read them and work what they add into the propositions: the figures in a table, what a chart shows and its key values, the wording of a document or a policy, a formula, above all what the speaker does not read out. Link a picture only where it shows the proposition beside it, not because it was on screen at that time: stock footage, a background, the speaker or a blank screen is not linked. The link text says what the picture shows, as `[<kind>：<what it shows>](frames/…)`; a picture whose content you cannot name in a few words that fit the point is not linked. There is no need to link every picture.
- **Keep what the video says apart from what you add.** Every proposition from the video comes from the transcript, a frame or a slide and carries its timestamp; link frames that support it. You may add what helps the reader beyond the video (background, how something works, a known correction), but start each addition with `补充：` and tag each premise you supply `补全`, so neither is taken for the speaker's words; never put words or pictures into the video that it does not have. Mark anything doubtful in the video `需确认` with its timestamp instead of guessing.
- **Claims belong to the speaker.** Write figures, news and opinions as what the video says ("视频称……", "作者认为……"), not as established fact, and keep the speaker's hedges and strength: what the speaker advises against stays advised against, not forbidden. Check them against other sources at length only when the user asks, in a separate section.
- **Clean the transcript of recurring mishearings; keep the original.** Speech recognition turns names and terms into homophones. Take the right form from the screen pages and frames (titles, slides, burned-in subtitles) or from context. A form that is wrong every time it occurs goes into the cleaned transcript (`video-agent fix`, which keeps `transcript.srt` as it was and writes `transcript.clean.*`, used from then on); a one-off mistake, or a form that is also a real word, is corrected only in the summary. When the right form is uncertain, mark it `需确认`.
- **One current version.** Rewrite `总结.md` in place when asked for changes; do not append update sections or save copies.

## 总结模板

每个视频一篇 `<视频文件夹>/总结.md`，写在 `process` 为它建的文件夹里，和 `summary-context.md` 放在一起。几个相关视频（一个合集、一门课的几讲）另写一篇 `<工作区>/合集总结.md`。模板定下标题和顺序；内容默认写透，用户要短时再压缩。

写法：

- 只链接确实存在的文件。视频文件夹里的文件用相对路径，如 `[字幕](transcript.txt)`、`[画面](frames/extra/frame-00-01-10.jpg)`；源视频用绝对路径，斜杠用 `/`；路径里有空格或方括号时写成 `[名字](<路径>)`，名字里的方括号写成 `\[`、`\]`。源视频写成普通文字的视频名加一个 `[打开视频](<路径>)` 链接：视频名是文件名去掉扩展名，再把下载工具为文件名替换的 `⧸`、`⧹` 换回 `/`、`\`，方括号照原样写，不用转义。
- 时间点统一写成 `HH:MM:SS`，放在反引号里。
- 命题编号写成粗体 `**P3**`，标签放在反引号里：`事实`、`观点`、`推断`、`引用`，总结者补出的前提标 `补全`。
- 某一节确实没有内容就删掉这一节，「需确认」除外：没有就写 `无`。

## 视频总结 `总结.md`

```markdown
# <视频标题>

视频：<视频名> · [打开视频](<源视频的绝对路径>) · 时长：<M:SS，一小时以上写 H:MM:SS> · 字幕：[transcript.txt](transcript.txt)（<来源：BCut 转录 / 内嵌字幕 / 字幕文件>）

## 元信息

- 类型：<课堂录像 / 讲座 / 访谈 / 教程 / 新闻 / 评论……>
- 讲者：<是谁，身份和立场，视频里看得出来时>
- 主题和范围：<讲什么、不讲什么，讲者自己说的目的>
- 预设：<讲者假定观众已经知道的内容；没有就删掉这一项>

### 需留意

不分真假、但要照办或记住的内容，附时间点：

- 点名、签到、小测：
- 作业和截止时间：
- 考核和评分标准：
- 课程要求：
- 考试和复习提示：
- 通知、链接和资源：

课堂录像写全这六项，没有的写 `无`；其他视频只写有的项，都没有就删掉这一小节。

## 概要

两到四句话：视频讲什么，主要结论是什么（附命题编号）。

## 论证结构

视频的主线：主要结论和它们靠什么成立。缩进表示支撑关系，每行只写编号、标签和一句简述，展开在「详细内容」里。

- **P9** `观点` 主要结论的简述
  - ← **P3** `事实` 简述
  - ← **P7** `推断` 简述
    - ← **P5** `引用` 简述
    - ← **P6** `补全` 简述

视频不论证（新闻、演示、按条讲授）时，按主题列出主要命题和它们之间的关系，或删掉这一节。

## 时间线

| 时间 | 内容 | 出处 |
| --- | --- | --- |
| `00:00:00` | 一句话说清这一段讲什么、为什么值得回看 | |
| `00:01:10` | 展示的图表或画面上的关键信息 | [<图表、截图……>：<图上是什么>](frames/extra/frame-00-01-10.jpg) |

## 详细内容

按视频自己的结构分段，每段一个小标题和时间范围，段里按命题写。数据、例子、步骤和表格放在它们支撑或说明的命题下面。写到没看视频的人也能明白这一段的程度。

### <段落标题> `00:12:30`–`00:25:10`

- **P1** `事实` `00:12:40` 规整后的命题。[<图表、截图……>：<图上是什么>](frames/...)
- **P2** `引用`（<来源>；讲者认同）`00:13:05` 规整后的命题。
- **P3** `推断` ← P1, P2 `00:14:10` 规整后的命题。
  - 形式：∀x (A(x) → B(x))。凡是 A 的都是 B，反过来不一定。
  - 例子：……
- **P4** `补全` P3 要成立还需要的前提，视频没有说。
- **P5** `观点` ← P3 `00:15:00` 规整后的命题。
  - 歧义：「原话」可以读作 (a) …… 或 (b) ……；取 (a)，因为……
- 补充：P3 只从两个例子推出全称结论。

## 需确认

- `00:03:20` 字幕听不清、前后矛盾、专有名词拿不准或歧义定不下来的地方
```

## 合集总结 `合集总结.md`

几个相关的视频（一门课、一个系列、一个播放列表）组成一个合集，合集总结写在合集文件夹里（`<工作区>/合集/<合集名>/合集总结.md`），链接各集的总结用相对路径 `../../<视频文件夹>/总结.md`。先有各集的总结，再写合集总结。

```markdown
# <合集名>

## 需留意

- 各集提到的截止时间、要做的事、考核要求、通知和资源，按时间先后，附出处：[<视频名> `00:42:10`](../../<视频文件夹>/总结.md)

## 各集一览

| # | 视频 | 时长 | 总结 | 需留意 | 一句话 |
| --- | --- | --- | --- | --- | --- |
| 1 | <视频名> | <M:SS> | [总结](../../<视频文件夹>/总结.md) | ✅ | 一句话，句末不加句号 |

## 主线

按主题而不是按视频顺序串起各集：每个主题一段，写各集的主要结论怎样接续、补充或修正，指向讲它的视频总结、时间点和命题编号（如 第 3 集 P7）。

## 跳过的视频

- <视频名>：跳过的原因（几乎没有讲话、只有几分钟、和其他集重复……）

## 需确认

- 各集之间矛盾的说法，附各自的视频、时间点和命题编号
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
