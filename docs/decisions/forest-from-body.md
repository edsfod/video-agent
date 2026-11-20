# 主线与单元 laid out by the program

Decided 2026-11-20 (user: 「认可这个，做吧」). Code: `src/video_agent/forest.py`; rules: `src/video_agent/prompts/summary.md` (二·关系, 三·主线与单元, 六·自查 6, the template); history of the forest itself: [summary-depth.md](summary-depth.md).

## The principle

A judgment is made once, by the model, in one place; whatever follows from it is done by the program; what the program can check it checks; judgment errors it cannot see are left to a targeted review.

| | Who | What |
| --- | --- | --- |
| Judgment | the model, in 详细内容 only | parts and their headings; each proposition's line (the claim, one sentence); relations `← P1`, `反驳 P4`, `步骤 P39`; under the main conclusion, `接上：` with the source of each link |
| Derivation | the program | trees, grouping by part, the main line, "from unit", each number linked to its entry |
| Checks | the program; later a review | form (a number with no proposition, a link to the main conclusion with no source); judgment errors (a relation left out or wrong, a part heading that does not cover its part) need the transcript and are for a review |

## How it came about

1. A rerun of lecture 1 with the 1.4.1 rules (14:10) no longer hung the Excel QR-code demonstration under the DSL idea, but left it out of 主线与单元, although 详细内容 wrote P37 ← P36. A check was added (relations in 详细内容 with an end missing from the forest). The user asked whether this was a prompt problem and for a better code or harness solution (「另外这会不会是提示词问题？我们能不能做个比较好的代码/harness 的解决方案？」). The same model and rules got it right in the next run (14:46; the Agent's own call of the checks found nothing), so the rule was followable and the miss a random omission in a long output, which more wording would not prevent.
2. Claude first dismissed building the forest from the relations, citing the choice of 2026-11-16 as "units are cut by what the speaker develops as a block, not by support relations". The user called that quoting out of context (「断章取义」), which it was: the user's words were 「「自包含」按什么划分——我不知道……算了，看来是乙」, the choice was against support relations *alone* (a cross link at 01:36 would fold the Excel thread into the main line), and the two identities of a unit, decided the same day, met that reason another way. Claude also proposed a check that a unit holds one tree, reading 「自身就是树」 (said against linking a unit outward) as a count, and three more checks of its own; all withdrawn (user: 「每人这么说过」, meant as 没人, and 「这是什么鬼」).
3. The user approved the program route (「可以做」). Claude's first design had the model write a skeleton (unit titles, roots) and a 简述 per item, with three ways to get the 简述; the user asked for a better design (「没有更好的办法吗？发挥你的设计才能？」). The second design took both from 详细内容: unit titles from part headings, 简述 as the proposition's line. The user asked whether losing topical units across parts and part headings as titles were acceptable, and how to balance a fitting structure, automation (few tokens) and few errors.
4. Answers, accepted: topical grouping of unrelated trees is the "relation made up to fill a unit" the rules forbid, and related material stays one tree across parts; part headings as unit titles were dropped, as the part 「计算机专业视角的复合实践：考试统分流水线」 (14:10) held the Excel tree too; a unit's title is its root's line, and part headings only group trees.
5. Asked whether the old design's strengths were kept (「另外旧的设计的优秀部分应该吸收了吧？」): see below; units of the writer's own (`拓展`) had been missed and were added.

## Evidence (2026-11-20, from the three drafts written with the 1.4.1 rules)

- Relations in the forest also written in 详细内容: 24 of 25 (lecture 1, 14:10), 23 of 23 (lecture 1, 14:46), 22 of 23 (lecture 2, 14:42). Drafts before 1.4.1 wrote many relations only in the forest; files already saved are not laid out again.
- Trees from 详细内容 grouped by their root's part reproduced the model's units: the same 8 units at 14:10 plus the Excel tree P36→P37 the model left out; 8 at 14:46, where the model had merged two parts with no relation between them; 6 at 14:42, where the model's 8 put P11 and P44 in two units each.
- The forest was 12–16% of the output; 时间线, partly derivable from the parts, 10–21%.
- Proposition lines (picture links aside) had a median of 70–92 characters, up to 199: too long to copy into a tree, hence one sentence per line with the particulars in lines under it.

## What the program does

- **Reads 详细内容.** An item is a line starting `- **P<n>**`; after the number come the tag, a time, a source in brackets and relation marks in any order, then the claim (picture links left out). `← P1, P2`: P1 and P2 support it. `反驳 P4`: it objects to P4. `步骤 P39`: it is a step of event P39. A line `` 接上：P18 讲者 `01:38:47`「……」；P48 总结者归纳 `` under an item makes it a main conclusion and links those items to it (a link written only there counts as a `←`).
- **Units.** Leaving the main conclusions out, the related items fall into groups; each group is laid out as a tree from a root that nothing stands above, an event with steps first, then the one reaching most items, then the first written. Trees go under the heading of the part of 详细内容 their root is in, parts in their order. Items related to nothing stay out.
- **Main line.** `### 主线` with the main conclusion, then each item linked to it: from a unit, named with `（来自单元：P<root>；<source>）` and nothing under it; otherwise (a quotation or filled-in premise, or a group whose items next to the main conclusion are all such) expanded there. A group next to the main conclusion with a link missing from `接上：` is still a unit, and the missing source is told as a problem.
- **Each item once.** The items next to an item are taken before any is expanded, so an item is expanded at its highest place; elsewhere it is named with `（在别处展开）`. An item standing on the one above it is written as in 详细内容 (`**P7** ← P5`); a step's event under the step as `（P5 是它的一步）`.
- **The section.** Replaces any 主线与单元 the writer wrote, keeping its `` ### `拓展` … `` units; without one, goes before the next section of the template present (时间线); with nothing related and no 拓展 unit, there is none. Each number is `[**P<n>**](#P<n>)`; the desktop app scrolls to the entry in 详细内容 and marks it for a moment.
- **Where.** On every import (Agent, chat AI rounds, files) and when `summarize` saves a model API's answer, when the template's 主线与单元 holds the mark `video-agent: 这一节由程序根据详细内容生成` (the built-in 标准 does). A template of the user's own without it is left to the writer. The checks no longer ask for the section and report what could not be laid out; the check added earlier the same day is gone.

## Kept from the model-written forest

The two identities of a unit (its own tree; what serves the main line, written in the main line with the unit named); the source of each link (`讲者接上` with time and words, not the speaker saying the point itself, else `总结者归纳`); a main conclusion of the summarizer's own in 「总结者归纳」 with its premises; events as roots with their steps; every item in one place; items related to nothing left out; an item that only illustrates another under it; quotations and filled-in premises supporting the main conclusion expanded in the main line; links to the main line belonging to it wherever said; units of the summarizer's own (`拓展`).

## Given up

Unit titles chosen by the model, and units grouping unrelated trees by topic. For a video that does not argue, the rule "units are the topics" goes with it: its forest is empty and the parts of 详细内容 carry the topics.

## Next

- Rerun both lectures with these rules and compare.
- A review for judgment errors with a slice of the transcript (discussed 2026-11-20, not decided): the parts' time ranges and the items' times give the range a question needs; a command such as `video-agent excerpt VIDEO 01:05:15-01:14:40` would print that stretch of `summary-context.md`; an Agent would be pointed at it, and a chat AI given it in a new conversation, its answer merged back by number.
- 时间线 could be derived the same way (one line per part); not done.
