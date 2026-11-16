# Writing a video summary

This file is shared by the Agent skill and the `summarize` command, so every route writes the same kind of summary. Print it with `video-agent template`.

## Rules

- **Keep what is worth noting, at the length it deserves.** 详细内容 is the body of the summary: go through the video part by part and keep what a viewer would want to note down, such as claims and the reasons given for them, figures, examples, demonstrations, steps, and what is shown on screen when it adds to what is said. The room a point gets follows what it is worth, not how long the video spends on it, nor a set size: a long stretch that says little gets a line, a short remark that carries an idea gets what it needs. Leave out repetition, filler, small talk and stretches with nothing worth noting (a break, setting up, talk off the subject) without accounting for them. Write notes a reader can scan, not the talk retold sentence by sentence in its order. Write in the language of the user's request, or of the video when there is no request.
- **要点 leaves out nothing important, in the video's order.** 要点 is what a reader who reads nothing else must take away, and it is complete: every conclusion, every idea the video develops (wherever it sits in 主线与单元), every demonstration or worked example the video spends real time on together with what it shows, and everything the speaker stresses or comes back to. One line each, in the order the video says them, with its time and proposition numbers; no grouping or classifying here, which is 主线与单元's job. Before finishing, go through 详细内容 part by part: a part with nothing in 要点 must hold nothing a reader needs to take away.
- **主线与单元: self-contained units first, then the main line they serve.** Where 要点 follows the video's time, 主线与单元 follows its logic, as a forest rather than one tree with everything hung on it (user decisions, 2026-11-16). First find the units. A unit is a stretch the speaker develops as a block, which a reader can take away on its own: an argument with its conclusion, or an event (a demonstration, a story, a case, an observation) with what it shows. Steps the speaker takes one after another in one go, such as a demonstration, what went wrong and how it was put right, are one unit, not one unit per step. Write each unit as a tree of its own: its root is that conclusion or event; indented under it, what supports the conclusion (`←`), or the steps of the event and what each shows, and under those what supports them. An event is the root or a step of its unit, never support for a conclusion it does not show. A unit is written as what it is on its own, with no link to another unit or to the main line. A demonstration used only to illustrate one point, with nothing of its own, is not a unit: it goes under that point. Units are not nested. Then the main line: when several units serve one higher conclusion, that conclusion is the main line, written first. What a unit gives the main line is written in the main line, not in the unit: under the main conclusion, the propositions that carry it there, often not the unit's root and often said elsewhere in the video, in passing or much later; each names the unit it comes from and how the link is known, `视频明说` with the time where the video makes it, or `总结者归纳` where the video leaves it implicit. A unit may give the main line nothing. A proposition used in several places is written once in 详细内容 and named by number elsewhere. When no conclusion is served by several units (an interview, a talk over separate topics), there is no main line; list the units. The main line comes first, then the units in the order the video first comes to them. Do not shrink a unit to what it gives the main line, nor to its example: write the idea it stands for on its own, as the video develops it.
- **Expand where the video is brief: what 拓展 is.** Do not stop at what the video says. A `拓展：` line is not what the video says put in another place, not general knowledge for its own sake and not a check of the video (that is `核对：`), but what a reader needs to understand or use the video and the video does not give: background, a definition, how something works, the concept, method or principle an example is a case of, a connection to a known result, a known counter-argument or correction (user decision, 2026-11-16). What the speaker says, even in passing, is a proposition or an event of the video in its place, never a 拓展. Put it under the point it serves; one that grows into an idea of its own is a unit marked `拓展`.
- **Separate what is claimed from what is asked.** What can be true or false (claims, figures, reasons, conclusions) is written as numbered propositions in 详细内容. What cannot (attendance, quizzes, assignments and deadlines, assessment and grading, course requirements, instructions, notices, links and resources) is not a proposition and goes into 元信息. Examples, demonstrations, tables and steps go under the proposition they illustrate or serve; a procedure taught as such is written as numbered steps, and what is claimed about it (why it works, when to use it) as propositions.
- **Tag each proposition by its standing in the video, not by whether it is true.** Ask in this order and take the first tag that fits:
  1. `引用`: the speaker attributes it to someone else (a paper, a book, a person, an institution, "有研究表明"). Name the source as the video gives it, and the speaker's stance: 认同, 反对 or 只转述. Check, as far as you know, that the attribution holds: that the source exists and says this. When it does not, or you cannot tell, say so in a `核对：` line under it.
  2. `观点`: it says what is good, right, important, advisable or likely, or how something should be understood, rather than what is the case: an evaluation, a recommendation, a norm, an interpretation or a prediction.
  3. `推断`: it says what is the case, and the video derives it from other propositions; list them as `← P2, P5`.
  4. `事实`: it says what is the case, without a derivation in the video: an observation, data, an event, how something works, a definition (written as `定义：<术语>指……`).
  An `观点` the video argues for lists its premises too. A tag records how the speaker presents a claim; `事实` is not a verdict that the claim is true.
- **Show the reasoning.** Number the propositions `P1`, `P2`… through the whole summary in the order they first appear. Where the video argues, write what supports or attacks what (`← P3`, `反驳 P4`). A premise a step needs but the video does not state is added as a proposition tagged `补全`: the weakest premise that makes the step work, marked as your reconstruction. 主线与单元 draws the units and the main line; everything else stays in 详细内容. Where the support is weaker than the conclusion (a general claim from a few examples, a correlation taken for a cause, a conclusion stronger than its premises), say so in a `核对：` line.
- **Make each proposition exact.** Rewrite what is said as a well-defined proposition: name the subject and what it is about; state the quantifier (all, most, some, in which cases, how many) and the conditions (if, only if, unless); replace words that depend on the moment ("这个", "这里", "我们", "现在", "去年") with what they refer to; give the time and scope it holds for. Keep the speaker's strength: "一般" does not become "总是", nor "可能" become "会".
  - Take the reading that someone who knows the subject would take in context, and among such readings the one the speaker most likely meant. Do not change what was said to make it true.
  - When a statement has several such readings and they would make materially different propositions, list them as options that exclude each other and together cover every case, say which you take and why, and add it to 需确认 when the context does not decide. When it has no such reading (the transcript is garbled and no frame helps), give the nearest guess and add it to 需确认.
  - Where words easily blur the structure (nested conditions, the order of quantifiers, a necessary against a sufficient condition, a definition against a claim about the thing defined), add a formal version (logic, sets or a formula) followed by one sentence in plain language. Elsewhere write naturally.
- **The pictures are material, not illustrations.** Screen pages and frames show text, tables, charts, documents, formulas, code and objects that the speech refers to or leaves out. Read them and work what they add into the propositions: the figures in a table, what a chart shows and its key values, the wording of a document or a policy, a formula, the steps of a demonstration, above all what the speaker does not read out. Link a picture only where it shows the proposition beside it, not because it was on screen at that time: stock footage, a background, the speaker or a blank screen is not linked. The link text says what the picture shows, as `[<kind>：<what it shows>](frames/…)`; a picture whose content you cannot name in a few words that fit the point is not linked. There is no need to link every picture.
- **Keep what the video says apart from what you add.** Every proposition from the video comes from the transcript, a frame or a slide and carries its timestamp; link frames that support it. What you add starts with `拓展：` (an expansion) or `核对：` (whether a source holds, whether support suffices), a premise you supply is tagged `补全` and a unit of your own is marked `拓展`, so none is taken for the speaker's words; never put words or pictures into the video that it does not have. Mark anything doubtful in the video `需确认` with its timestamp instead of guessing.
- **Claims belong to the speaker.** Write figures, news and opinions as what the video says ("视频称……", "作者认为……"), not as established fact, and keep the speaker's hedges and strength: what the speaker advises against stays advised against, not forbidden. Apart from checking attributions (above) and the corrections you add, check claims against other sources at length only when the user asks, in a separate section.
- **Clean the transcript of recurring mishearings; keep the original.** Speech recognition turns names and terms into homophones. Take the right form from the screen pages and frames (titles, slides, burned-in subtitles) or from context. A form that is wrong every time it occurs goes into the cleaned transcript (`video-agent fix`, which keeps `transcript.srt` as it was and writes `transcript.clean.*`, used from then on); a one-off mistake, or a form that is also a real word, is corrected only in the summary. When the right form is uncertain, mark it `需确认`.
- **One current version.** Rewrite `总结.md` in place when asked for changes; do not append update sections or save copies.

## 总结模板

每个视频一篇 `<视频文件夹>/总结.md`，写在 `process` 为它建的文件夹里，和 `summary-context.md` 放在一起。几个相关视频（一个合集、一门课的几讲）另写一篇 `<工作区>/合集总结.md`。模板定下标题和顺序；每一点写多少看它值多少。

写法：

- 只链接确实存在的文件。视频文件夹里的文件用相对路径，如 `[字幕](transcript.txt)`、`[画面](frames/extra/frame-00-01-10.jpg)`；源视频用绝对路径，斜杠用 `/`；路径里有空格或方括号时写成 `[名字](<路径>)`，名字里的方括号写成 `\[`、`\]`。源视频写成普通文字的视频名加一个 `[打开视频](<路径>)` 链接：视频名是文件名去掉扩展名，再把下载工具为文件名替换的 `⧸`、`⧹` 换回 `/`、`\`，方括号照原样写，不用转义。
- 时间点统一写成 `HH:MM:SS`，放在反引号里。
- 命题编号写成粗体 `**P3**`，标签放在反引号里：`事实`、`观点`、`推断`、`引用`，总结者补出的前提标 `补全`。
- 总结者自己加的内容另起一行。`拓展：` 不是把视频讲过的话换个地方再说一遍，也不是和视频无关的常识，而是视频没讲、读者要看懂或用上它所需要的东西：背景、定义、原理、它是哪个已知概念或方法的一个例子、已知的反驳或更正。`核对：` 写出处对不对、支撑够不够。
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

两到四句话：视频讲什么，主要结论是什么（附命题编号），有哪些重要的单元。

## 要点

读者只读这一节也不能漏掉的东西，按视频的先后排，不分类，每条一句，附时间点和命题编号：结论和视频展开的想法、讲者花了时间的演示或例子和它说明了什么、讲者强调或反复回到的内容。

- `00:12:40` 一句话写清这一点（**P3**、**P7**）
- `00:30:10` 演示或例子：做了什么，说明了什么（**P12**）

## 主线与单元

先找单元：讲者成块讲的一段，单看也能带走的东西，是一个结论和它的论证，或一个事件（演示、故事、案例、观测）和它说明了什么。讲者一口气讲下来、前后相承的几步（演示、出了什么问题、怎么改好）是一个单元，不按步骤切开。每个单元自成一棵树，只写它自身：不连到别的单元，也不连到主线；事件是单元的起点或其中一步，不当作它并不证明的结论的支撑。单元不嵌套。再看几个单元是否共同服务一个更高的结论：有，它就是主线，写在最前；各单元为主线贡献的东西写在主线里，不写在单元里；没有就不写主线。单元按视频第一次讲到它的先后排。每行只写编号、标签和一句简述，展开在「详细内容」里。

### 主线：<主要结论的简述>

- **P50** `观点` 主要结论的简述
  - ← **P53** `观点` 简述（来自单元：<单元名>；视频明说 `01:36:50`）
  - ← **P41** `推断` 简述（来自单元：<另一个单元名>；总结者归纳）
    - ← **P40** `事实` 简述
  - ← **P45** `引用` 简述
  - ← **P46** `补全` 简述

### <单元名> `01:09:28`–`01:24:16`

- **P39** `事实` 起点事件：做了什么、发生了什么
  - **P40** `事实` 下一步：出了什么问题
  - **P42** `事实` 再下一步：怎么改好
    - **P43** `观点` ← P42 这个单元自身得出的道理
  - 拓展：视频没讲、看懂这一点需要的背景或原理

### <单元名> `00:30:10`–`00:41:20`

- **P12** `观点` 这个单元的结论
  - ← **P10** `事实` 简述
    - ← **P9** `引用` 简述
  - ← **P11** `推断` 简述

### `拓展` <单元名>

- 总结者拓展出的一个完整想法，和它为什么有助于理解视频

视频不论证（新闻、演示、按条讲授）时，单元就是各个话题，列出主要命题和它们之间的关系，没有主线。

## 时间线

| 时间 | 内容 | 出处 |
| --- | --- | --- |
| `00:00:00` | 一句话说清这一段讲什么、为什么值得回看 | |
| `00:01:10` | 展示的图表或画面上的关键信息 | [<图表、截图……>：<图上是什么>](frames/extra/frame-00-01-10.jpg) |

## 详细内容

按视频自己的结构分段，每段一个小标题和时间范围，段里按命题写；一个单元较长时单独成段。数据、例子、步骤和表格放在它们支撑或说明的命题下面；需要背景、原理或一般道理才看得懂的地方，用「拓展：」展开。写到没看视频的人也能明白、能用上的程度。

### <段落标题> `00:12:30`–`00:25:10`

- **P1** `事实` `00:12:40` 规整后的命题。[<图表、截图……>：<图上是什么>](frames/...)
- **P2** `引用`（<来源>；讲者认同）`00:13:05` 规整后的命题。
  - 核对：这个出处确实这样说 / 出处里的说法其实是……
- **P3** `推断` ← P1, P2 `00:14:10` 规整后的命题。
  - 形式：∀x (A(x) → B(x))。凡是 A 的都是 B，反过来不一定。
  - 例子：……
- **P4** `补全` P3 要成立还需要的前提，视频没有说。
- **P5** `观点` ← P3 `00:15:00` 规整后的命题。
  - 歧义：「原话」可以读作 (a) …… 或 (b) ……；取 (a)，因为……
  - 拓展：这个做法背后的一般原理是……
- 核对：P3 只从两个例子推出全称结论。

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

按主题而不是按视频顺序串起各集：每个主题一段，写各集的主要结论怎样接续、补充或修正，指向讲它的视频总结、时间点和命题编号（如 第 3 集 P7）。各集的单元在后面几集被接上或用到的，也写在这里。

## 跳过的视频

- <视频名>：跳过的原因（几乎没有讲话、只有几分钟、和其他集重复……）

## 需确认

- 各集之间矛盾的说法，附各自的视频、时间点和命题编号
```

「需留意」那一列：这一集的总结里有「需留意」的内容就打 ✅。没有跳过的视频就删掉那一节。每写完或改完一集的总结，就把它并进合集总结：需留意、一览里的那一行、主线里相关的主题。

## 学习提纲 `学习提纲.md`

用户要复习、自学或准备考试时，在合集文件夹里写学习提纲。它根据各集的总结、字幕和画面写；视频以外的内容只以「拓展：」或「核对：」出现；范围按用户的要求，默认是整个合集。

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
