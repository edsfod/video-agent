# Summarizing articles

Requested 2026-11-20; designed, nothing built yet. The plan and what is left are below.

## What the user asked for

- 「这个 skill 其实整理一下还可以用来快速总结后读别人的文章」 (`_Problems.md`, 2026-11-20).
- 「skill 总结文章只要是一个 skill 就行，我用在其他地方」, and asked whether it needs the program.
- On Claude's three questions (2026-11-20):
  - A summary to read in place of the article or a map before reading it: both, in one document, as a video summary has a quick view and the full body together (「我觉得完整和地图都要在一起才是完整，就像现在的 skill 也分两个但是都在同一篇文档内一样」); the article itself is most likely not read afterwards (「快速总结后读不是说读原文，大概率是不读原文的」). Claude had first offered a switch between the two; dropped.
  - Where: an agent that may or may not run code; possibly through the program too; also as a standalone skill and as a plugin or npx package (「可能可以可能不行，或许也可以接入程序，然后也有单体 skill 型态？也有插件/npx 型态？」).
  - What: anything, plain text, text with pictures, or PDF; places need not be marked finely, pages perhaps not at all (「页面可能不需要标，或许没必要那么细致？」).
- The forms in this order: one shared core of rules, a standalone skill, the program, then plugin and npx (「在这个 baseline 上 redesign，型态大概是这个顺序。没做的得记下来。」).

## Design

**The reader** has not read the article and most likely will not: as for a video, the summary is written for someone who reads it instead.

**One document, a quick view and the full body**, as for a video:

| Section | For an article |
| --- | --- |
| 元信息 | type, author and standing, where and when published (link), topic and scope, 预设; 需留意 only when the article asks something of its readers |
| 概要 | as for a video |
| 要点 | in the article's order, each with its section instead of a time |
| 主线与单元 | laid out by the program from 详细内容 ([forest-from-body.md](forest-from-body.md)) |
| 详细内容 | the body, one part per section of the article (its heading as the part's title, no time range); propositions carry no position of their own; figures and tables read into the propositions and named by their number in the article, or described when unnumbered |
| 需确认 | as for a video |

Left out: 时间线 (the parts already follow the article's sections), 字幕改正, 画面调整, anything about frames and subtitles. No page numbers.

**Input** is read by the agent itself: a web page, a file of text, a PDF, with pictures where the agent can see them.

**One source of rules.** `prompts/summary.md` is split into a core both kinds share (who the summary is for, items, tags, sources, relations, 拓展 and 核对, how to write a proposition, 主线与单元, the shared checks) and a part for each kind (video: times, pictures, subtitles, 需留意 for courses, 时间线, the template; article: places, figures, the template). The video template and the article rules are put together from these, so a rule changed in the core changes both; `forest.py` stays one program for both.

## Forms, in order

1. **Shared core.** Split the rules; the video template comes out the same in substance; a test keeps the generated article rules up to date with their sources.
2. **Standalone skill** (`skills/article-summary/`): SKILL.md, the article rules put together, and `forest.py` as a script (it needs only Python's `re`). An agent that runs Python writes the draft, runs the script to lay out 主线与单元 and fixes what it reports; one that cannot writes the section itself by a fallback the rules carry (the model-written forest of 1.4.1, with its higher error rate).
3. **The program**: a command such as `video-agent article <URL or file>` with a folder per article, reusing import, versions, checks and the forest; the agent still reads the article. The desktop app is left as it is for now.
4. **Plugin and npx**: a Claude Code plugin is the same skill folder packaged; npx is Node's, so it needs the forest in JavaScript or a call to Python. Whether a ready npx installer for skills exists, and how it works, was not checked.

## Not done

- All four forms above.
- The fallback rules for writing 主线与单元 by hand when no script can run.
- What 需留意 holds for an article, and whether its 元信息 needs more (such as the article's own claims about its evidence), to be seen on real articles.
- Trying it on a few articles of each kind (plain text, with pictures, PDF).
