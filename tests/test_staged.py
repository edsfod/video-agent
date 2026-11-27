"""The staged summary (staged.py): the program's checks, merges and marks, agy's events, and a whole run through a
scripted channel."""

import io
import json
import re
from pathlib import Path

import pytest

from video_agent import staged, staged_agy, summary_data, versions
from video_agent.evidence import SUMMARY_NAME
from video_agent.processor import process_video


@pytest.fixture
def processed(sample_video, tmp_path):
  workspace = tmp_path / 'work'
  process_video(sample_video, workspace, interval=2, max_frames=6, status=lambda message: None)
  return sample_video, workspace


DRAFT = """## 正文

- **S0** `观点` `00:00:02` 乙。
- **S1** 支撑 S0 `事实` `00:00:01` 甲公司的流水线把每个单元交给一个对话来写，程序检查以后只把查出的问题发回原对话。
  - 子行一
  - 子行二

## 画面

- #1–#3 无新内容：彩条
- #4 无用：重复 #1

## 补截

无

## 归属意见

无

## 边界

无
"""


def test_a_fix_replaces_what_it_names_and_keeps_sub_lines_it_leaves_out():
  patch = """## 正文

- **S1** 支撑 S0 `事实` `00:00:01` 改过的命题行。
- **S2** 展开 S0 `事实` `00:00:03` 新加的。
  - 新子行

## 画面

- #2 用在 S1：图上是什么。读出（上半）：`x`

## 归属意见

- 应属于 L2：它讲的是另一个话题
"""
  text, changed = staged.merge(DRAFT, patch)
  assert changed == 2
  found = staged.blocks(staged.section(text, '正文'))
  assert (
    found['S1'] == '- **S1** 支撑 S0 `事实` `00:00:01` 改过的命题行。\n  - 子行一\n  - 子行二'
  )  # the sub-lines stay
  assert list(found) == ['S0', 'S1', 'S2']
  shown = staged.section(text, '画面').splitlines()
  assert (
    shown[0].startswith('- #1、#3 无新内容') and shown[1].startswith('- #2 用在 S1') and shown[2].startswith('- #4')
  )
  assert staged.section(text, '归属意见') == '- 应属于 L2：它讲的是另一个话题'


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


def test_a_pointer_is_a_short_line_that_names_only_the_act():
  assert staged.pointer('- **S5** `事实` `00:01:00` 细化受控隔离机场景的信道条件。')
  assert staged.pointer('- **S2** 支撑 S0 `事实` 讲者展示了一个表格。')
  assert not staged.pointer(
    '- **S3** `事实` 讲者展示了一份充斥论文却缺乏开源代码仓库与个人主页的脱敏简历，在导师筛选中被判定为可信度极低。'
  )


def test_units_run_to_the_next_start_and_are_named_by_their_start():
  units = staged.parse_units(
    '## 单元\n- `00:01:00` 乙 | 演示 | 二 | 岔出 `00:00:00`\n- `00:00:00` 甲 | 话题 | 一 | L1\n- `00:02:00` 休息 | 略过 |\n',
    300,
  )
  assert [u['attach'] for u in units] == ['L1', '岔出 `00:00:00`', '']
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


def test_a_unit_is_a_tree_under_its_head_and_its_pictures_hang_on_items():
  unit = {'id': 'U000000', 'start': 0, 'end': 60, 'title': '甲', 'kind': '论证'}
  draft = (
    '## 正文\n\n- **S0** `观点` `00:00:40` 结论。\n- **S1** 支撑 S0 `事实` `00:00:10` 前提。\n  - 细节\n'
    '- **S2** `事实` `00:00:20` 没挂上。\n- **S3** 步骤 S9 `00:00:30` 父节点不在。\n'
    '- **S4** 支撑 S0 反驳 S1 `00:00:31` 两个父节点。\n- **S5** `推断` ← S1 旧写法。\n\n'
    '## 画面\n\n- #1–#2 用在 S1、S0：表格。读出（上半）：`x`\n- #3 无用：转场\n- #4 用在 S8：图\n'
  )
  data, problems = summary_data.unit_data(unit, draft, {1: 'a.jpg', 2: 'b.jpg', 3: 'c.jpg', 4: 'd.jpg'}, staged.section)
  assert problems == [
    'S2 没有写父节点：在编号后面写「支撑／反驳／步骤／展开 S<n>」',
    'S4 写了 2 个父节点，只能有一个',
    'S5 用了「←」：关系写在子节点上，每个条目写自己的父节点，例如「支撑 S0」',
    'S3 的父节点 S9 不存在',
    '「## 画面」里的 S8 不存在',
  ]
  items = {item['id']: item for item in data['items']}
  assert (items['S1']['parent'], items['S1']['edge'], items['S1']['time'], items['S1']['details']) == (
    'S0',
    '支撑',
    10,
    '- 细节',
  )
  assert items['S1']['pictures'] == [{'path': 'a.jpg', 'caption': '表格'}, {'path': 'b.jpg', 'caption': '表格'}]
  assert [(depth, item['id']) for depth, item in summary_data.tree(data)][:3] == [(0, 'S0'), (1, 'S1'), (1, 'S4')]
  ring = summary_data.read_items('- **S0** 头\n- **S1** 支撑 S2 甲\n- **S2** 支撑 S1 乙\n')[1]
  assert 'S1 往上的父节点连成了环' in ring
  assert summary_data.read_items('- **S1** 支撑 S0 甲 [图](a.jpg)\n')[1][0].startswith('没有头 **S0**')


def test_the_whole_holds_together_or_says_where_not():
  units = ['U000000', 'U000100', 'U000200', 'U000300', 'U000400']
  lines = summary_data.read_lines('- L1 话题：甲\n  - 主结论：U000100\n- L2 话题：乙\n- L3\n')
  assert lines[0] == {'id': 'L1', 'topic': '甲', 'conclusions': [{'unit': 'U000100'}]}
  edges = summary_data.read_edges(
    '- U000000 支撑 U000100 | 讲者 `00:01:30`：讲者说前面的例子证明了这一点 | 贡献：例子 X 说明 Y\n'
    '- `00:02:00` 铺垫 U000300\n- U000400 续 U000100\n'
  )
  assert edges[0] == {
    'from': 'U000000',
    'kind': '支撑',
    'to': 'U000100',
    'source': {'by': '讲者', 'time': 90, 'said': '讲者说前面的例子证明了这一点'},
    'contribution': '例子 X 说明 Y',
  }
  attach = '- U000000 L1\n- U000100 L1\n- U000200 岔出 U000100\n- U000300 岔出 U000000–U000100\n- U000300 L2\n'
  problems, found = summary_data.whole_problems(units, attach, lines, edges)
  assert found['U000300'] == {'side': {'between': ['U000000', 'U000100']}}
  assert problems == [
    'U000300 写了不止一个归属',
    'U000400 没有归属',
    'L3 没有话题',
    'L2 没有单元',
    'L3 没有单元',
    'U000300 标成了旁支，但 U000200 对它有铺垫关系：有单元依赖它，它不是旁支',
    'U000200 标成了旁支，但它铺垫 U000300：推进别的单元的不是旁支',
    'U000400 续 U000100：「续」的两端要在同一条主线里',
  ]
  # a member of a mainline with a conclusion that no edge leads from is found
  problems, _ = summary_data.whole_problems(
    units[:3], '- U000000 L1\n- U000100 L1\n- U000200 L1\n', lines[:1], edges[:1]
  )
  assert problems == ['U000200 属于 L1，但沿推进边走不到它的主结论：漏了推进边，或归属写错了']


def test_the_markdown_shows_the_mainlines_then_every_unit_whole():
  item = lambda key, parent, edge, time, text: {
    'id': key,
    'parent': parent,
    'edge': edge,
    'time': time,
    'labels': ['事实'],
    'text': text,
    'details': '',
    'pictures': [],
  }
  unit = lambda uid, start, title, attach, items: {
    'id': uid,
    'start': start,
    'end': start + 60,
    'title': title,
    'kind': '论证',
    'attach': attach,
    'items': items,
  }
  data = {
    'title': '标题',
    'video': '视频：x',
    'meta': ['类型：测试'],
    'notices': [],
    'abstract': '讲者用 U000000 论证了 U000100.S0。',
    'unsure': [],
    'units': [
      unit(
        'U000000',
        0,
        '例子',
        {'line': 'L1'},
        [item('S0', None, None, 30, '例子说明 Y。'), item('S1', 'S0', '步骤', 10, '先做 A。')],
      ),
      unit('U000100', 60, '结论', {'line': 'L1'}, [item('S0', None, None, 70, '所以 Z。')]),
      unit('U000200', 120, '题外话', {'side': {'unit': 'U000000'}}, [item('S0', None, None, 125, '顺便一提。')]),
    ],
    'lines': [{'id': 'L1', 'topic': '为什么 Z', 'conclusions': [{'unit': 'U000100'}]}],
    'edges': [
      {
        'from': 'U000000',
        'to': 'U000100',
        'kind': '支撑',
        'source': {'by': '总结者归纳'},
        'contribution': 'Y 是 Z 的一例',
      }
    ],
  }
  text = summary_data.markdown(data)
  assert '讲者用「例子」论证了「结论」S0。' in text
  assert (
    '### 为什么 Z\n\n- 主结论 「结论」：所以 Z。\n  - 支撑：「例子」：Y 是 Z 的一例（总结者归纳）\n    - 旁支 「题外话」：顺便一提。\n'
    in text
  )
  assert (
    '### 例子 `00:00:00`–`00:01:00`\n\n论证 · 主线：为什么 Z\n\n- **S0** `事实` `00:00:30` 例子说明 Y。\n  - **S1** 步骤 · `事实` `00:00:10` 先做 A。\n'
    in text
  )
  assert '论证 · 旁支，从「例子」岔出' in text


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
ADDS = {'00:00:00': '合成画面没有声音以外的信息。', '00:00:04': '竖条从左到右依次变暗。'}


WHOLE = (
  '## 主线\n- L1 话题：测试图\n  - 主结论：U000004\n\n'
  '## 推进\n- U000000 铺垫 U000004 | 总结者归纳 | 贡献：先说明后面的画面是合成的\n'
)


class Channel:
  """A scripted agy: the main conversation's turns and each unit's first draft, with fixed usage."""

  NAME, MODEL, FIX_MODEL = 'fake', 'model-high', 'model-medium'

  def __init__(self):
    self.prompts = []

  def turn(self, prompt, workspace, log, *, conversation=None, model=None):
    self.prompts.append((prompt, conversation, model))
    if prompt.startswith('你是视频总结流水线的主对话'):
      reply = (
        '## 改正\n无\n\n## 锚点\n无\n\n## 无内容\n无\n\n## 主线\n- L1 话题：测试图\n\n'
        '## 单元\n- `00:00:00` 开场 | 话题 | 讲者说要讲什么 | L1\n- `00:00:04` 图表 | 演示 | 看图表 | L1\n\n'
        '## 推进\n- `00:00:00` 铺垫 `00:00:04`\n\n## 事项\n无\n\n## 元信息\n- 类型：测试\n\n## 连接处\n无\n'
      )
    elif prompt.startswith('最后一轮'):  # one unit left without an attachment, for the check to find
      reply = (
        f'{WHOLE}\n## 归属\n- U000004 L1\n\n## 概要\n讲者用 U000004 演示了测试图。\n\n## 元信息\n- 类型：测试\n\n'
        '## 需留意\n- 点名、签到、小测：无\n\n## 需确认\n无\n'
      )
    elif prompt.startswith('程序检查了「## 主线」'):
      reply = f'{WHOLE}\n## 归属\n- U000000 L1\n- U000004 L1\n'

    else:
      start = re.search(r'（`(\d\d:\d\d:\d\d)`–', prompt)[1]
      count = len(re.findall(r'^- #\d+ ', prompt.split('===== 画面清单 =====')[1], re.MULTILINE))
      second = staged.clock(staged.seconds(start) + 1)
      reply = (
        f'## 正文\n\n- **S0** `事实` `{second}` {SAYS[start]}\n'
        f'  - 子行\n- **S1** 展开 S0 `事实` `{second}` {ADDS[start]}\n\n## 画面\n\n'
        + (f'- #1–#{count} 用在 S0：彩条\n' if count else '无\n')
        + '\n## 补截\n\n## 事项\n无\n\n## 预设\n无\n\n## 需确认\n无\n\n## 归属意见\n无\n\n## 边界\n无\n'
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


def test_a_whole_run_writes_each_unit_in_its_own_conversation_and_saves_the_tokens(processed, monkeypatch):
  video, workspace = processed
  channel = Channel()
  monkeypatch.chdir(workspace.parent)  # the workspace given as a relative path, as `-o video-agent-output` is
  run = staged.Run(video, Path(workspace.name), status=lambda message: None, channel=channel)
  target = run.go()
  assert target.name == SUMMARY_NAME
  text = target.read_text(encoding='utf-8')
  assert '- **S0** `事实` `00:00:01`' in text and '- **S0** `事实` `00:00:05`' in text
  assert (
    '- 主结论 「图表」：后半段换成' in text and '  - 铺垫：「开场」：先说明后面的画面是合成的（总结者归纳）' in text
  )
  assert '讲者用「图表」演示了测试图。' in text
  data = json.loads((run.dir / 'summary.json').read_text(encoding='utf-8'))
  assert [u['attach'] for u in data['units']] == [{'line': 'L1'}, {'line': 'L1'}]
  assert run.record['whole_problems'] == []
  # M1, M3 and its fix in the main conversation, one conversation per unit; all on the first model
  conversations = [conversation for _, conversation, _ in channel.prompts]
  assert conversations == [None, None, None, 'c1', 'c1'] and {model for *_, model in channel.prompts} == {'model-high'}
  assert '- U000000 没有归属' in channel.prompts[4][0]
  current = versions.listing(target)['current']
  assert current['source'] == 'fake 分阶段'
  assert current['data'] and versions.data_of(target)['units'][0]['id'] == 'U000000'  # the data is kept with it
  assert current['usage'] == {'calls': 5, 'input': 50, 'cache_read': 25, 'output': 15, 'thinking': 10}
  assert (run.dir / 'imported').is_file()
  # a run that is done is not gone on with: the next one starts afresh
  assert staged.Run(video, workspace, status=lambda message: None, channel=channel).dir != run.dir
  # the pictures a unit is told to open have absolute paths, which agy needs
  shown = re.findall(r'打开这些总图（每格左下角印着编号和时间）：(\S+?)。', channel.prompts[1][0])
  assert shown and all(Path(path).is_absolute() for path in shown[0].split('、'))


def test_what_the_model_copies_from_the_prompt_is_taken_out_of_the_body():
  text = '## 正文\n\n- **S1** 甲\n  - 子行：乙\n  - 画面读出（上半、左下）：丙\n\n## 画面\n\n- #1 用在 S1：图。读出（上半）：丁\n'
  assert (
    staged.clean(text)
    == '## 正文\n\n- **S1** 甲\n  - 乙\n  - 画面：丙\n\n## 画面\n\n- #1 用在 S1：图。读出（上半）：丁\n'
  )
