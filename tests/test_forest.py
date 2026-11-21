"""主线与单元 laid out by the program from the relations in 详细内容 (forest.py)."""

import re
import time

from video_agent import forest, summary_review, templates

BODY = """## 详细内容

### 开场 `00:00:00`–`00:10:00`

- **P1** `事实` `00:01:00` 一个观测。[画面：图](frames/run/frame-001-00-01-00.jpg)
  - 场景和数字写在子行。
- **P2** `观点` ← P1 `00:02:00` 由观测得出的道理。
- **P3** `事实` `00:03:00` 和谁都没有关系的一条。

### 演示 `00:10:00`–`00:20:00`

- **P4** `事实` `00:11:00` 讲者做了一个演示。
- **P5** `事实` 步骤 P4 `00:12:00` 出了问题。
- **P6** `事实` 步骤 P4 `00:14:00` 改好了。
- **P7** `观点` ← P6, P5 `00:15:00` 演示说明的道理。
- **P8** `观点` 反驳 P7 `00:16:00` 有人不同意。
- **P9** `引用`（某书；讲者认同）`00:17:00` 书里的话。
  - **P10** `事实` 书里的一个例子，写在子行也算一条。

### 总结者归纳

- **P11** `总结者归纳` ← P2, P7, P9 主结论。
  - 接上：P2 讲者 `00:19:00`「所以说……」；P7 总结者归纳
"""


def test_related_items_become_trees_under_their_part_and_the_main_line_takes_what_joins_it():
  section, problems = forest.build(BODY)
  assert problems == []
  # The main line: what the units give it, named with their unit and where the link comes from; a quotation that
  # supports it directly is expanded there.
  assert section.startswith('## 主线与单元\n\n### 主线\n\n- [**P11**](#P11) `总结者归纳` 主结论。\n')
  assert '  - ← [**P2**](#P2) `观点` 由观测得出的道理。（来自单元：P2；讲者 `00:19:00`「所以说……」）' in section
  assert '  - ← [**P7**](#P7) `观点` 演示说明的道理。（来自单元：P4；总结者归纳）' in section
  assert '  - ← [**P9**](#P9) `引用`（某书；讲者认同） 书里的话。' in section
  # A unit is a tree under the heading of its root's part, the root's line its title; picture links are left out.
  assert '### 开场\n\n- [**P2**](#P2) `观点` 由观测得出的道理。\n  - ← [**P1**](#P1) `事实` 一个观测。\n' in section
  assert '[画面' not in section
  # The event: its steps under it, what a step shows under the step, the objection under what it objects to; P6, a
  # step of the event, is expanded there and only named under P7.
  assert (
    '### 演示\n\n- [**P4**](#P4) `事实` 讲者做了一个演示。\n'
    '  - [**P5**](#P5) `事实` 出了问题。\n'
    '    - [**P7**](#P7) `观点` ← P5 演示说明的道理。\n'
    '      - ← [**P6**](#P6) `事实` 改好了。（在别处展开）\n'
    '      - 反驳 [**P8**](#P8) `观点` 有人不同意。\n'
    '  - [**P6**](#P6) `事实` 改好了。\n'
  ) in section
  # Related to nothing: only in 详细内容.
  assert 'P3' not in section and 'P10' not in section


def test_what_the_program_cannot_lay_out_is_told_to_the_writer():
  text = BODY.replace('；P7 总结者归纳', '') + '- **P13** `观点` ← P99 用了不存在的编号。\n'
  _, problems = forest.build(text)
  assert any('P99' in problem for problem in problems)
  assert any(
    problem.startswith('P7 接到了主结论 P11，「接上」里却没写') and '时间和转述' in problem for problem in problems
  )


def test_no_main_line_without_a_join_and_no_section_without_relations():
  section, _ = forest.build(BODY.replace('  - 接上：P2 讲者 `00:19:00`「所以说……」；P7 总结者归纳\n', ''))
  assert '### 主线' not in section and '[**P11**]' in section
  assert forest.build('## 详细内容\n\n### 一段 `00:00:00`–`00:01:00`\n\n- **P1** `事实` 一条。\n') == ('', [])


def test_the_section_is_put_in_place_of_the_writers_and_keeps_units_of_the_writers_own():
  rules = templates.built_in(templates.STANDARD)
  assert forest.wanted(rules)
  written = (
    '# 标题\n\n## 要点\n\n- 一点（**P2**）\n\n## 主线与单元\n\n### 模型自己排的\n\n- **P2** 简述\n\n'
    '### `拓展` 总结者的想法\n\n- 一个完整的想法\n\n' + BODY
  )
  text, _ = forest.place(written, rules)
  assert '模型自己排的' not in text and '### `拓展` 总结者的想法\n\n- 一个完整的想法' in text
  assert text.index('## 要点') < text.index('### 主线') < text.index('### `拓展`') < text.index('## 详细内容')
  # Left out by the writer, the section goes where the template has it.
  text, _ = forest.place(
    written.replace(written[written.index('## 主线与单元') : written.index('## 详细内容')], ''), rules
  )
  assert text.index('## 要点') < text.index('## 主线与单元') < text.index('## 详细内容')
  # A template of the user's own that has the writer write the section is left alone.
  assert forest.place(written, '## 主线与单元\n\n照我说的写\n') == (written, [])


def test_points_link_their_numbers_and_bring_the_pictures_of_their_items():
  rules = templates.built_in(templates.STANDARD)
  body = BODY.replace('出了问题。\n', '出了问题。\n  - 报错的画面 [截图：报错](frames/run/frame-002.jpg)\n').replace(
    '改好了。\n', '改好了。[截图：改好](<frames/run/frame 003.jpg>)\n'
  )
  items, _ = forest.parse(body)
  assert items['5'].pictures == ['[截图：报错](frames/run/frame-002.jpg)'] and items['5'].claim == '出了问题。'
  assert items['1'].pictures == ['[画面：图](frames/run/frame-001-00-01-00.jpg)'] and items['11'].pictures == []
  written = (
    '# 标题\n\n## 要点\n\n'
    '- `00:01:00`–`00:02:00` 观测和道理（**P2**、**P1**）\n'
    '- `00:11:00`–`00:15:00` 演示（**P4**）和 P7\n'
    '- `00:16:00`–`00:17:00` 没有画面（**P8**、**P99**）\n\n' + body
  )
  text, _ = forest.place(written, rules)
  # An item's own pictures, or with none those of the items right under it as premises or steps, each picture once.
  assert (
    '- `00:01:00`–`00:02:00` 观测和道理（[**P2**](#P2)、[**P1**](#P1)） · '
    '[画面：图](frames/run/frame-001-00-01-00.jpg)\n'
  ) in text
  assert (
    '- `00:11:00`–`00:15:00` 演示（[**P4**](#P4)）和 P7 · [截图：报错](frames/run/frame-002.jpg) · '
    '[截图：改好](<frames/run/frame 003.jpg>)\n'
  ) in text
  # An attack is not what a point stands on; a number not in 详细内容 stays as written.
  assert '- `00:16:00`–`00:17:00` 没有画面（[**P8**](#P8)、**P99**）\n' in text
  assert forest.place(text, rules)[0] == text
  # A template that leaves 主线与单元 to the writer leaves 要点 alone too.
  assert forest.place(written, '## 主线与单元\n\n照我说的写\n') == (written, [])


def test_points_clean_stray_dots_after_drop_links_and_keep_pictures_after_join():
  rules = templates.built_in(templates.STANDARD)
  body = (
    BODY.replace(
      '一个观测。[画面：图](frames/run/frame-001-00-01-00.jpg)',
      r'一个观测。[画面：\[A\] 图](frames/run/frame-001.jpg) [画面：图2](frames/run/frame-002.jpg)',
    ).rstrip()
    + '\n  - 总结图 [画面：总览](frames/run/frame-011.jpg)\n'
  )
  items, _ = forest.parse(body)
  assert items['1'].pictures == [r'[画面：\[A\] 图](frames/run/frame-001.jpg)', '[画面：图2](frames/run/frame-002.jpg)']
  assert items['11'].pictures == ['[画面：总览](frames/run/frame-011.jpg)']
  first = (
    '# 标题\n\n## 要点\n\n'
    '- `00:01:00`–`00:02:00` 观测（**P1**）\n'
    '- `00:18:00`–`00:20:00` 总结（**P11**）\n'
    '- `00:01:00`–`00:02:00` 已有图（**P1**） [画面：图2](frames/run/frame-002.jpg)\n\n' + body
  )
  round1, _ = forest.place(first, rules)
  assert (
    r'- `00:01:00`–`00:02:00` 观测（[**P1**](#P1)） · [画面：\[A\] 图](frames/run/frame-001.jpg) · '
    '[画面：图2](frames/run/frame-002.jpg)\n'
  ) in round1
  assert '- `00:18:00`–`00:20:00` 总结（[**P11**](#P11)） · [画面：总览](frames/run/frame-011.jpg)\n' in round1
  # A picture already on the point line is not appended a second time.
  assert (
    r'- `00:01:00`–`00:02:00` 已有图（[**P1**](#P1)） [画面：图2](frames/run/frame-002.jpg) · '
    r'[画面：\[A\] 图](frames/run/frame-001.jpg)' + '\n'
  ) in round1
  # When a review round drops pictures before forest.place runs, no stray ' ·' stays on the point line.
  dropped, _ = summary_review.drop_links(
    round1, {'pictures': {'frames/run/frame-001.jpg': '', 'frames/run/frame-011.jpg': ''}}
  )
  round2, _ = forest.place(dropped, rules)
  assert '- `00:01:00`–`00:02:00` 观测（[**P1**](#P1)） · [画面：图2](frames/run/frame-002.jpg)\n' in round2
  assert '- `00:18:00`–`00:20:00` 总结（[**P11**](#P11)）\n' in round2


def test_points_take_only_bold_numbers_and_the_pictures_of_a_parent_after_a_nested_item():
  rules = templates.built_in(templates.STANDARD)
  body = BODY.replace(
    '  - **P10** `事实` 书里的一个例子，写在子行也算一条。\n',
    '  - **P10** `事实` 书里的一个例子，写在子行也算一条。\n  - 书的封面 [画面：封面](<frames/run/frame 09.jpg>)\n',
  )
  items, _ = forest.parse(body)
  # A line back at the parent's depth after a nested item is the parent's again.
  assert items['9'].pictures == ['[画面：封面](<frames/run/frame 09.jpg>)'] and items['10'].pictures == []
  written = (
    '# 标题\n\n## 要点\n\n'
    '- `00:17:00`–`00:18:00` 讲 P2P 网络和冯·诺依曼（**P9**、**P3**）·\n'
    '- `00:17:00`–`00:18:00` 同一张图另一种写法（**P9**） [封面](frames/run/frame%2009.jpg)\n\n' + body
  )
  text, _ = forest.place(written, rules)
  # P2P is not P2, a '·' in a word stays, and a picture is one file however its path is written.
  assert (
    '- `00:17:00`–`00:18:00` 讲 P2P 网络和冯·诺依曼（[**P9**](#P9)、[**P3**](#P3)）· · '
    '[画面：封面](<frames/run/frame 09.jpg>)\n'
  ) in text
  assert '- `00:17:00`–`00:18:00` 同一张图另一种写法（[**P9**](#P9)） [封面](frames/run/frame%2009.jpg)\n' in text
  assert forest.place(text, rules)[0] == text


def test_picture_links_on_a_line_with_many_backslashes_are_found_at_once():
  formula = r'- **P1** `事实` `00:01:00` 公式 \[ ' + ' + '.join([r'\alpha_i'] * 40) + r' \] [图](frames/a.jpg)'
  start = time.perf_counter()
  assert re.findall(forest.LINK, formula) == ['[图](frames/a.jpg)']
  assert [m[1] for m in summary_review.LINK.finditer(formula)] == ['frames/a.jpg']
  assert time.perf_counter() - start < 1


def test_an_agents_draft_is_saved_with_the_section_laid_out_and_told_what_the_program_could_not_lay_out(
  sample_video, tmp_path, capsys
):
  from video_agent import cli
  from video_agent.processor import asset_folder, process_video

  workspace = tmp_path / 'work'
  process_video(sample_video, workspace, interval=2, max_frames=6, status=lambda message: None)
  draft = asset_folder(workspace, sample_video.resolve()) / '总结.draft.md'
  draft.write_text('# 标题\n\n## 要点\n\n- 一点（**P2**）\n\n' + BODY.replace('；P7 总结者归纳', ''), encoding='utf-8')
  assert cli.main(['summarize', str(sample_video), '-o', str(workspace), '--import']) == 0
  saved = (draft.parent / '总结.md').read_text(encoding='utf-8')
  assert saved.index('## 要点') < saved.index('## 主线与单元\n\n### 主线') < saved.index('## 详细内容')
  told = capsys.readouterr().err
  assert '检查：P7 接到了主结论 P11，「接上」里却没写' in told and '「主线与单元」' not in told


def test_a_numbered_list_of_points_is_linked_too_and_a_bare_p_number_points_to_no_part():
  rules = templates.built_in(templates.STANDARD)
  written = (
    '# 标题\n\n## 要点\n\n1. `00:01:00`–`00:02:00` 观测（**P1**）\n2) `00:03:00`–`00:04:00` 讲 P3P 协议\n\n' + BODY
  )
  text, _ = forest.place(written, rules)
  assert '1. `00:01:00`–`00:02:00` 观测（[**P1**](#P1)） · [画面：图](frames/run/frame-001-00-01-00.jpg)\n' in text
  # P3P is a word, not P3: a point that names only it points to no part.
  assert '开场' in summary_review.unlisted_parts('## 要点\n\n- 讲 P3P 协议\n\n' + BODY)
