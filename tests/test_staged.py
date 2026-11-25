"""The staged summary (staged.py): the program's checks, merges and marks, agy's events, and a whole run through a
scripted channel."""

import io
import json
import re

import pytest

from video_agent import staged, staged_agy, versions
from video_agent.evidence import SUMMARY_NAME
from video_agent.processor import process_video


@pytest.fixture
def processed(sample_video, tmp_path):
  workspace = tmp_path / 'work'
  process_video(sample_video, workspace, interval=2, max_frames=6, status=lambda message: None)
  return sample_video, workspace


DRAFT = """## 正文

- **S1** `事实` `00:00:01` 甲公司的流水线把每个单元交给一个对话来写，程序检查以后只把查出的问题发回原对话。
  - 子行一
  - 子行二
- **S2** `观点` `00:00:02` ← S1 乙。[屏幕页：图](frames/a.jpg)

## 画面

- #1–#3 无新内容：彩条
- #4 无用：重复 #1

## 补截

无

## 要点候选

- S1：旧的

## 边界

无
"""


def test_a_fix_replaces_what_it_names_and_keeps_sub_lines_it_leaves_out():
  patch = """## 正文

- **S1** `事实` `00:00:01` 改过的命题行。
- **S3** `事实` `00:00:03` 新加的。
  - 新子行

## 画面

- #2 用在 S1：图上是什么。读出（上半）：`x`

## 要点候选

- S1：新的
"""
  text, changed = staged.merge(DRAFT, patch)
  assert changed == 2
  found = staged.blocks(staged.section(text, '正文'))
  assert found['S1'] == '- **S1** `事实` `00:00:01` 改过的命题行。\n  - 子行一\n  - 子行二'  # the sub-lines stay
  assert list(found) == ['S1', 'S2', 'S3']
  shown = staged.section(text, '画面').splitlines()
  assert (
    shown[0].startswith('- #1、#3 无新内容') and shown[1].startswith('- #2 用在 S1') and shown[2].startswith('- #4')
  )
  assert staged.section(text, '要点候选') == '- S1：新的'


def test_formulas_read_off_pictures_are_marked_once_and_commands_are_not():
  text = (
    '## 正文\n\n- **S1** `事实` `00:00:01` 公式 `=1+MOD(INT(NOW()*86400/A$40), 3)` 和命令 '
    '`$ lsusb 2>/dev/null; echo "---"` 和短的 `=A1+1`，核过的 `=SUM(B2:B90)+SUM(C2:C9)`。\n\n## 画面\n\n- #1 `=X`\n'
  )
  marked, count = staged.mark_unchecked(text, checked={'=SUM(B2:B90)+SUM(C2:C9)'})
  assert count == 1
  assert '`=1+MOD(INT(NOW()*86400/A$40), 3)`（AI 未核对）' in marked
  assert staged.mark_unchecked(marked, checked={'=SUM(B2:B90)+SUM(C2:C9)'})[1] == 0  # marked already
  assert '## 画面\n\n- #1 `=X`\n' in marked


def test_links_to_pictures_the_unit_drops_go_to_the_one_they_repeat_or_away():
  text = '## 正文\n\n- **S1** 甲 [图](a.jpg) 乙 [图](b.jpg) 丙 [图](c.jpg)\n\n## 画面\n\n- #2 无用：重复 #1\n'
  paths = {1: 'a.jpg', 2: 'b.jpg', 3: 'c.jpg'}
  fixed, count = staged.unlink_dropped(text, paths, {'b.jpg': '重复 #1', 'c.jpg': '转场'})
  assert count == 2
  assert '- **S1** 甲 [图](a.jpg) 乙 [图](a.jpg) 丙\n' in fixed


def test_a_pointer_is_a_short_line_that_names_only_the_act():
  assert staged.pointer('- **S5** `事实` `00:01:00` 细化受控隔离机场景的信道条件。')
  assert staged.pointer('- **S2** `事实` 讲者展示了一个表格。')
  assert not staged.pointer(
    '- **S3** `事实` 讲者展示了一份充斥论文却缺乏开源代码仓库与个人主页的脱敏简历，在导师筛选中被判定为可信度极低。'
  )


def test_units_run_to_the_next_start_and_are_named_by_their_start():
  units = staged.parse_units(
    '## 单元\n- `00:01:00` 乙 | 演示 | 二\n- `00:00:00` 甲 | 话题 | 一\n- `00:02:00` 休息 | 略过 |\n', 300
  )
  assert [(u['id'], u['start'], u['end'], u['skip']) for u in units] == [
    ('U000000', 0, 60, False),
    ('U000100', 60, 120, False),
    ('U000200', 120, 300, True),
  ]
  assert staged.unit_problems(units, 300) == []
  assert staged.unit_problems(units[2:], 300) == ['第一个单元没有从视频开头开始']
  assert staged.objections({'U1': '## 边界\n无', 'U2': '## 边界\n- 起点应挪到 `00:01:10`'}) == {
    'U2': '- 起点应挪到 `00:01:10`'
  }


def test_the_program_writes_the_points_from_the_propositions_the_main_conversation_names():
  units = staged.parse_units('## 单元\n- `00:00:00` 甲 | 论证 | 一\n- `00:01:00` 乙 | 演示 | 二\n', 120)
  drafts = {
    'U000000': '## 正文\n\n- **S1** `事实` `00:00:10` 前提。\n- **S2** `观点` `00:00:40` ← S1 结论。[图](f.jpg)\n',
    'U000100': '## 正文\n\n- **S1** `事实` `00:01:05` 演示。\n',
  }
  whole = '## 主结论\n无\n\n## 要点\n- P2\n- P3\n\n## 概要\n概要。\n\n## 元信息\n- 类型：测试\n\n## 需留意\n无\n\n## 需确认\n无\n'
  text = staged.assemble(units, drafts, whole, '# 标题\n\n视频：x')
  assert '- `00:00:10`–`00:00:40` 结论。（**P2**）' in text
  assert '- `00:01:05` 演示。（**P3**）' in text
  assert '- **P2** `观点` `00:00:40` ← P1 结论。' in text
  assert '### 乙 `00:01:00`–`00:02:00`' in text


def test_a_turns_usage_is_the_sum_of_its_calls_failed_ones_included():
  usage = lambda n: {'input_tokens': n, 'cache_read_tokens': 1, 'output_tokens': 2, 'thinking_tokens': 1}
  events = [
    {'conversation_id': 'c1'},
    {'event': 'step_update', 'step_update': {'state': 'DONE', 'step_type': 'agent_response', 'usage': usage(10)}},
    {'event': 'step_update', 'step_update': {'state': 'ERROR', 'step_type': 'agent_response', 'usage': usage(5)}},
    {'event': 'step_update', 'step_update': {'state': 'DONE', 'step_type': 'tool', 'tool_name': 'view_file'}},
    {'event': 'result', 'result': {'status': 'SUCCESS', 'response': '## 正文', 'usage': {'input_tokens': 999}}},
  ]
  found = staged_agy.parse('\n'.join(json.dumps(e) for e in events))
  assert found['conversation'] == 'c1' and found['calls'] == 1 and found['failed'] == 1 and found['tools'] == 1
  assert found['usage'] == {'input': 15, 'cache_read': 2, 'output': 4, 'thinking': 2}
  with pytest.raises(staged_agy.ChannelError):
    staged_agy.parse(json.dumps({'event': 'result', 'result': {'status': 'ERROR', 'error': 'quota'}}))


def test_the_hook_lets_agy_read_only_inside_the_workspace(tmp_path):
  call = lambda name, path: io.StringIO(json.dumps({'toolCall': {'name': name, 'args': {'AbsolutePath': str(path)}}}))
  assert staged_agy.gate(tmp_path, call('view_file', tmp_path / 'a.jpg'))['decision'] == 'allow'
  assert staged_agy.gate(tmp_path, call('view_file', tmp_path.parent / 'b.jpg'))['decision'] == 'deny'
  assert staged_agy.gate(tmp_path, call('run_command', tmp_path / 'a.jpg'))['decision'] == 'deny'


SAYS = {
  '00:00:00': '开场时讲者先说今天要讲一个测试视频，听众由此知道后面的画面都是合成的。',
  '00:00:04': '后半段换成七条彩色竖条组成的标准测试图，用来核对显示器的颜色。',
}


class Channel:
  """A scripted agy: the main conversation's turns and each unit's first draft, with fixed usage."""

  NAME, MODEL, FIX_MODEL = 'fake', 'model-high', 'model-medium'

  def __init__(self):
    self.prompts = []

  def turn(self, prompt, workspace, log, *, conversation=None, model=None):
    self.prompts.append((prompt, conversation, model))
    if prompt.startswith('你是视频总结流水线的主对话'):
      reply = (
        '## 改正\n无\n\n## 锚点\n无\n\n## 无内容\n无\n\n## 单元\n- `00:00:00` 开场 | 话题 | 讲者说要讲什么\n'
        '- `00:00:04` 图表 | 演示 | 看图表\n\n## 事项\n无\n\n## 元信息\n- 类型：测试\n\n## 主结论\n无\n\n## 连接处\n无\n'
      )
    elif prompt.startswith('最后一轮'):
      reply = (
        '## 主结论\n无\n\n## 接上\n无\n\n## 要点\n- P1\n- P2\n\n## 概要\n测试视频的概要。\n\n## 元信息\n- 类型：测试\n\n'
        '## 需留意\n- 点名、签到、小测：无\n\n## 需确认\n无\n'
      )
    else:
      start = re.search(r'（`(\d\d:\d\d:\d\d)`–', prompt)[1]
      count = len(re.findall(r'^- #\d+ ', prompt.split('===== 画面清单 =====')[1], re.MULTILINE))
      second = staged.clock(staged.seconds(start) + 1)
      reply = (
        f'## 正文\n\n- **S1** `事实` `{second}` {SAYS[start]}\n'
        '  - 子行\n\n## 画面\n\n'
        + (f'- #1–#{count} 无新内容：彩条\n' if count else '无\n')
        + '\n## 补截\n\n## 事项\n无\n\n## 预设\n无\n\n## 需确认\n无\n\n## 要点候选\n- S1：要点\n\n## 边界\n无\n'
      )
    return {
      'conversation': conversation or f'c{len(self.prompts)}',
      'response': reply,
      'calls': 1,
      'failed': 0,
      'tools': 0,
      'tool_names': {},
      'denied': [],
      'usage': {'input': 10, 'cache_read': 5, 'output': 3, 'thinking': 2},
      'seconds': 0.1,
    }


def test_a_whole_run_writes_each_unit_in_its_own_conversation_and_saves_the_tokens(processed):
  video, workspace = processed
  channel = Channel()
  run = staged.Run(video, workspace, status=lambda message: None, channel=channel)
  target = run.go()
  assert target.name == SUMMARY_NAME
  text = target.read_text(encoding='utf-8')
  assert '- **P1** `事实` `00:00:01`' in text and '- **P2** `事实` `00:00:05`' in text
  assert '## 要点\n\n- `00:00:01` ' in text
  # M1 and M3 in the main conversation, one conversation per unit; the main and unit turns on the first model
  conversations = [conversation for _, conversation, _ in channel.prompts]
  assert conversations == [None, None, None, 'c1'] and {model for *_, model in channel.prompts} == {'model-high'}
  current = versions.listing(target)['current']
  assert current['source'] == 'fake 分阶段'
  assert current['usage'] == {'calls': 4, 'input': 40, 'cache_read': 20, 'output': 12, 'thinking': 8}
  assert (run.dir / 'imported').is_file()
  # a run that is done is not gone on with: the next one starts afresh
  assert staged.Run(video, workspace, status=lambda message: None, channel=channel).dir != run.dir
