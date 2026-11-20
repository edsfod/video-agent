"""主线与单元 laid out by the program from the relations in 详细内容 (forest.py)."""

from video_agent import forest, templates

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
  assert any(problem.startswith('P7 接到了主结论 P11，「接上」里却没写') for problem in problems)


def test_no_main_line_without_a_join_and_no_section_without_relations():
  section, _ = forest.build(BODY.replace('  - 接上：P2 讲者 `00:19:00`「所以说……」；P7 总结者归纳\n', ''))
  assert '### 主线' not in section and '[**P11**]' in section
  assert forest.build('## 详细内容\n\n### 一段 `00:00:00`–`00:01:00`\n\n- **P1** `事实` 一条。\n') == ('', [])


def test_the_section_is_put_in_place_of_the_writers_and_keeps_units_of_the_writers_own():
  rules = templates.built_in(templates.STANDARD)
  assert forest.wanted(rules)
  written = (
    '# 标题\n\n## 要点\n\n- 一点（**P2**）\n\n## 主线与单元\n\n### 模型自己排的\n\n- **P2** 简述\n\n'
    '### `拓展` 总结者的想法\n\n- 一个完整的想法\n\n## 时间线\n\n| 时间 | 内容 |\n\n' + BODY
  )
  text, _ = forest.place(written, rules)
  assert '模型自己排的' not in text and '### `拓展` 总结者的想法\n\n- 一个完整的想法' in text
  assert text.index('## 要点') < text.index('### 主线') < text.index('### `拓展`') < text.index('## 时间线')
  # Left out by the writer, the section goes where the template has it.
  text, _ = forest.place(
    written.replace(written[written.index('## 主线与单元') : written.index('## 时间线')], ''), rules
  )
  assert text.index('## 要点') < text.index('## 主线与单元') < text.index('## 时间线')
  # A template of the user's own that has the writer write the section is left alone.
  assert forest.place(written, '## 主线与单元\n\n照我说的写\n') == (written, [])


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
