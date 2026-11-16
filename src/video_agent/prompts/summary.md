# Writing a video summary

This file is shared by the Agent skill and the `summarize` command, so every route writes the same kind of summary. Print it with `video-agent template`.

## Rules

- **Keep what is worth noting, at the length it deserves.** 详细内容 is the body of the summary: go through the video part by part and keep what a viewer would want to note down, such as claims and the reasons given for them, figures, examples, demonstrations, steps, and what is shown on screen when it adds to what is said. The room a point gets follows what it is worth, not how long the video spends on it, nor a set size: a long stretch that says little gets a line, a short remark that carries an idea gets what it needs. Leave out repetition, filler, small talk and stretches with nothing worth noting (a break, setting up, talk off the subject) without accounting for them. Write notes a reader can scan, not the talk retold sentence by sentence in its order. Write in the language of the user's request, or of the video when there is no request.
- **要点 leaves out nothing important, in the video's order.** 要点 is what a reader who reads nothing else must take away, and it is complete: every conclusion, every idea the video develops (wherever it sits in 主线与旁路), every demonstration or worked example the video spends real time on together with what it shows, and everything the speaker stresses or comes back to. One line each, in the order the video says them, with its time and proposition numbers; no grouping or classifying here, which is 主线与旁路's job. Before finishing, go through 详细内容 part by part: a part with nothing in 要点 must hold nothing a reader needs to take away.
- **主线与旁路: by theme, in logical order.** Where 要点 follows the video's time, 主线与旁路 follows its logic. Group the content by theme; within a theme, order it logically and show the structure by indentation: under a conclusion, what supports it (`←`); under a point, a side path that branches off from it. A talk is seldom one line with everything hung on it: the main line is the video's main conclusions and what they rest on, and a side path (旁路) is anything else that carries an idea of its own, such as a demonstration that leads to a general point, a digression the speaker develops, a method shown through one example, a story told for its lesson. Put a side path under the point it branches off from, marked `旁路`, with what it shows or argues, the general idea it leads to, and where it joins the main line again, if it does; its own propositions are indented under it. Do not hang a side path as support under a conclusion it does not support, and do not shrink it to its example: write the idea the example stands for as the video develops it, including what is said about it in passing or much later. A theme may come back at several times in the video; it is still one group.
- **Expand where the video is brief.** Do not stop at what the video says. Add what a reader needs to understand or use it: background, a definition, how something works, the general principle an example stands for when the video only hints at it, a connection to a known concept, method or result, a known counter-argument or correction. Put an addition under the point it serves, as a line starting with `补充：`; an addition that grows into an idea of its own is a side path marked `补充`. Add what helps a reader understand and use the video, not general knowledge for its own sake.
- **Separate what is claimed from what is asked.** What can be true or false (claims, figures, reasons, conclusions) is written as numbered propositions in 详细内容. What cannot (attendance, quizzes, assignments and deadlines, assessment and grading, course requirements, instructions, notices, links and resources) is not a proposition and goes into 元信息. Examples, demonstrations, tables and steps go under the proposition they illustrate or serve; a procedure taught as such is written as numbered steps, and what is claimed about it (why it works, when to use it) as propositions.
- **Tag each proposition by its standing in the video, not by whether it is true.** Ask in this order and take the first tag that fits:
  1. `引用`: the speaker attributes it to someone else (a paper, a book, a person, an institution, "有研究表明"). Name the source as the video gives it, and the speaker's stance: 认同, 反对 or 只转述. Check, as far as you know, that the attribution holds: that the source exists and says this. When it does not, or you cannot tell, say so in a `补充：` line under it.
  2. `观点`: it says what is good, right, important, advisable or likely, or how something should be understood, rather than what is the case: an evaluation, a recommendation, a norm, an interpretation or a prediction.
  3. `推断`: it says what is the case, and the video derives it from other propositions; list them as `← P2, P5`.
  4. `事实`: it says what is the case, without a derivation in the video: an observation, data, an event, how something works, a definition (written as `定义：<术语>指……`).
  An `观点` the video argues for lists its premises too. A tag records how the speaker presents a claim; `事实` is not a verdict that the claim is true.
- **Show the reasoning.** Number the propositions `P1`, `P2`… through the whole summary in the order they first appear. Where the video argues, write what supports or attacks what (`← P3`, `反驳 P4`). A premise a step needs but the video does not state is added as a proposition tagged `补全`: the weakest premise that makes the step work, marked as your reconstruction. 主线与旁路 draws the main line and the side paths; everything else stays in 详细内容. Where the support is weaker than the conclusion (a general claim from a few examples, a correlation taken for a cause, a conclusion stronger than its premises), say so in a `补充：` line.
- **Make each proposition exact.** Rewrite what is said as a well-defined proposition: name the subject and what it is about; state the quantifier (all, most, some, in which cases, how many) and the conditions (if, only if, unless); replace words that depend on the moment ("这个", "这里", "我们", "现在", "去年") with what they refer to; give the time and scope it holds for. Keep the speaker's strength: "一般" does not become "总是", nor "可能" become "会".
  - Take the reading that someone who knows the subject would take in context, and among such readings the one the speaker most likely meant. Do not change what was said to make it true.
  - When a statement has several such readings and they would make materially different propositions, list them as options that exclude each other and together cover every case, say which you take and why, and add it to 需确认 when the context does not decide. When it has no such reading (the transcript is garbled and no frame helps), give the nearest guess and add it to 需确认.
  - Where words easily blur the structure (nested conditions, the order of quantifiers, a necessary against a sufficient condition, a definition against a claim about the thing defined), add a formal version (logic, sets or a formula) followed by one sentence in plain language. Elsewhere write naturally.
- **The pictures are material, not illustrations.** Screen pages and frames show text, tables, charts, documents, formulas, code and objects that the speech refers to or leaves out. Read them and work what they add into the propositions: the figures in a table, what a chart shows and its key values, the wording of a document or a policy, a formula, the steps of a demonstration, above all what the speaker does not read out. Link a picture only where it shows the proposition beside it, not because it was on screen at that time: stock footage, a background, the speaker or a blank screen is not linked. The link text says what the picture shows, as `[<kind>：<what it shows>](frames/…)`; a picture whose content you cannot name in a few words that fit the point is not linked. There is no need to link every picture.
- **Keep what the video says apart from what you add.** Every proposition from the video comes from the transcript, a frame or a slide and carries its timestamp; link frames that support it. What you add starts with `补充：`, a premise you supply is tagged `补全` and a side path of your own is marked `补充`, so none is taken for the speaker's words; never put words or pictures into the video that it does not have. Mark anything doubtful in the video `需确认` with its timestamp instead of guessing.
- **Claims belong to the speaker.** Write figures, news and opinions as what the video says ("视频称……", "作者认为……"), not as established fact, and keep the speaker's hedges and strength: what the speaker advises against stays advised against, not forbidden. Apart from checking attributions (above) and the corrections you add, check claims against other sources at length only when the user asks, in a separate section.
- **Clean the transcript of recurring mishearings; keep the original.** Speech recognition turns names and terms into homophones. Take the right form from the screen pages and frames (titles, slides, burned-in subtitles) or from context. A form that is wrong every time it occurs goes into the cleaned transcript (`video-agent fix`, which keeps `transcript.srt` as it was and writes `transcript.clean.*`, used from then on); a one-off mistake, or a form that is also a real word, is corrected only in the summary. When the right form is uncertain, mark it `需确认`.
- **One current version.** Rewrite `总结.md` in place when asked for changes; do not append update sections or save copies.

## 总结模板

每个视频一篇 `<视频文件夹>/总结.md`，写在 `process` 为它建的文件夹里，和 `summary-context.md` 放在一起。几个相关视频（一个合集、一门课的几讲）另写一篇 `<工作区>/合集总结.md`。模板定下标题和顺序；每一点写多少看它值多少。

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

两到四句话：视频讲什么，主要结论是什么（附命题编号），有哪些重要的旁路。

## 要点

读者只读这一节也不能漏掉的东西，按视频的先后排，不分类，每条一句，附时间点和命题编号：结论和视频展开的想法、讲者花了时间的演示或例子和它说明了什么、讲者强调或反复回到的内容。

- `00:12:40` 一句话写清这一点（**P3**、**P7**）
- `00:30:10` 演示或例子：做了什么，说明了什么（**P12**）

## 主线与旁路

按主题分组；每个主题里按逻辑顺序排，用缩进表示结构：结论下面是支撑它的命题（`←`），一点下面是从它分出的旁路，旁路自己的命题再缩进在它下面。每行只写编号、标签和一句简述，展开在「详细内容」里。同一主题在视频里前后出现几次，也合在一组。

### <主题>

- **P9** `观点` 主要结论的简述
  - ← **P3** `事实` 简述
  - ← **P7** `推断` 简述
    - ← **P5** `引用` 简述
    - ← **P6** `补全` 简述
  - **P5** `事实` 简述
    - `旁路` **<旁路名>** `00:30:10`–`00:41:20`：引出的一般道理；在 **P20** `01:12:00` 接回主线（没有接回就不写这一句）
      - **P12** `事实` 演示了什么
      - **P14** `观点` ← P12 它说明的道理
    - `旁路` `补充` **<旁路名>**：总结者拓展的内容，和它为什么有助于理解这一点

### <另一个主题>

- ……

视频不论证（新闻、演示、按条讲授）时，按主题列出主要命题和它们之间的关系。

## 时间线

| 时间 | 内容 | 出处 |
| --- | --- | --- |
| `00:00:00` | 一句话说清这一段讲什么、为什么值得回看 | |
| `00:01:10` | 展示的图表或画面上的关键信息 | [<图表、截图……>：<图上是什么>](frames/extra/frame-00-01-10.jpg) |

## 详细内容

按视频自己的结构分段，每段一个小标题和时间范围，段里按命题写；旁路较长时单独成段。数据、例子、步骤和表格放在它们支撑或说明的命题下面；需要背景、原理或一般道理才看得懂的地方，用「补充：」展开。写到没看视频的人也能明白、能用上的程度。

### <段落标题> `00:12:30`–`00:25:10`

- **P1** `事实` `00:12:40` 规整后的命题。[<图表、截图……>：<图上是什么>](frames/...)
- **P2** `引用`（<来源>；讲者认同）`00:13:05` 规整后的命题。
  - 补充：这个出处确实这样说 / 出处里的说法其实是……
- **P3** `推断` ← P1, P2 `00:14:10` 规整后的命题。
  - 形式：∀x (A(x) → B(x))。凡是 A 的都是 B，反过来不一定。
  - 例子：……
- **P4** `补全` P3 要成立还需要的前提，视频没有说。
- **P5** `观点` ← P3 `00:15:00` 规整后的命题。
  - 歧义：「原话」可以读作 (a) …… 或 (b) ……；取 (a)，因为……
  - 补充：这个做法背后的一般原理是……
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

按主题而不是按视频顺序串起各集：每个主题一段，写各集的主要结论怎样接续、补充或修正，指向讲它的视频总结、时间点和命题编号（如 第 3 集 P7）。各集的旁路在后面几集被接上或用到的，也写在这里。

## 跳过的视频

- <视频名>：跳过的原因（几乎没有讲话、只有几分钟、和其他集重复……）

## 需确认

- 各集之间矛盾的说法，附各自的视频、时间点和命题编号
```

「需留意」那一列：这一集的总结里有「需留意」的内容就打 ✅。没有跳过的视频就删掉那一节。每写完或改完一集的总结，就把它并进合集总结：需留意、一览里的那一行、主线里相关的主题。

## 学习提纲 `学习提纲.md`

用户要复习、自学或准备考试时，在合集文件夹里写学习提纲。它根据各集的总结、字幕和画面写；视频以外的内容只以「补充：」出现；范围按用户的要求，默认是整个合集。

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
