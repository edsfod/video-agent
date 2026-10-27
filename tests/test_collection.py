"""Collections: membership, shared terms, states, the overview and the study guide."""

import io
import json
import shutil

import pytest

from video_agent import cli, collection
from video_agent.processor import asset_folder
from video_agent.summarize import SummaryError, summarize_collection

OVERVIEW = (
  '# 测试合集\n\n## 各集一览\n\n| # | 视频 | 时长 | 总结 | 需留意 | 一句话 |\n| --- | --- | --- | --- | --- | --- |\n'
)


@pytest.fixture
def two_videos(sample_video, tmp_path):
  """The sample and a copy with its own subtitles, so they are two different videos."""
  second = tmp_path / 'media' / 'part two.mp4'
  second.parent.mkdir()
  shutil.copyfile(sample_video, second)
  shutil.copyfile(sample_video.with_suffix('.srt'), second.with_suffix('.srt'))
  return sample_video.resolve(), second.resolve()


def _show(workspace, name, capsys):
  capsys.readouterr()
  assert cli.main(['collection', 'show', name, '-o', str(workspace)]) == 0
  return json.loads(capsys.readouterr().out)


def test_members_keep_their_order_and_shared_terms_reach_every_transcript(two_videos, tmp_path, capsys):
  first, second = two_videos
  workspace = tmp_path / 'work'
  assert cli.main(['process', str(first), '-o', str(workspace), '--frame-interval', '2']) == 0
  assert cli.main(['collection', 'create', '课程 A', str(second), '-o', str(workspace)]) == 0
  assert cli.main(['collection', 'add', '课程 A', str(first), str(second), '--at', '1', '-o', str(workspace)]) == 0
  shown = _show(workspace, '课程 A', capsys)
  assert [member['video'] for member in shown['videos']] == [str(first), str(second)], 'added once, at the front'
  assert [member['processed'] for member in shown['videos']] == [True, False]

  assert cli.main(['collection', 'terms', '课程 A', '--replace', '测试视频', '示例视频', '-o', str(workspace)]) == 0
  assert '今天讲示例视频' in (asset_folder(workspace, first) / 'transcript.clean.txt').read_text(encoding='utf-8')
  # A member processed later gets the terms too.
  assert cli.main(['process', str(second), '-o', str(workspace), '--frame-interval', '2']) == 0
  assert '今天讲示例视频' in (asset_folder(workspace, second) / 'summary-context.md').read_text(encoding='utf-8')

  # Short and almost wordless: maybe empty. Skipping keeps it in the list with the reason.
  shown = _show(workspace, '课程 A', capsys)
  assert all(member['maybe_empty'] for member in shown['videos'])
  assert cli.main(['collection', 'skip', '课程 A', str(second), '--reason', '只有 8 秒', '-o', str(workspace)]) == 0
  assert _show(workspace, '课程 A', capsys)['videos'][1]['skipped'] == '只有 8 秒'

  # Leaving the collection takes its terms away; deleting it leaves the videos' folders.
  assert cli.main(['collection', 'remove', '课程 A', str(first), '-o', str(workspace)]) == 0
  assert not (asset_folder(workspace, first) / 'transcript.clean.txt').exists()
  assert cli.main(['collection', 'delete', '课程 A', '-o', str(workspace)]) == 0
  assert not (workspace / '合集' / '课程 A').exists() and asset_folder(workspace, second).is_dir()
  assert not (asset_folder(workspace, second) / 'transcript.clean.txt').exists()


def test_overview_and_guide_from_the_summaries(two_videos, tmp_path, capsys, fake_model, no_proxy, monkeypatch):
  first, second = two_videos
  workspace = tmp_path / 'work'
  for video in (first, second):
    assert cli.main(['process', str(video), '-o', str(workspace), '--frame-interval', '2']) == 0
  collection.create(workspace, '系列', [first, second])
  (asset_folder(workspace, first) / '总结.md').write_text('# 第一集\n\n讲了测试视频。\n', encoding='utf-8')
  config = {'provider': 'openai', 'model': 'test', 'base_url': ''}

  with pytest.raises(SummaryError, match='no summary yet'):
    summarize_collection(workspace, '系列', config, 'key', status=lambda message: None)
  collection.skip(workspace, '系列', second, '和第一集重复')

  capsys.readouterr()
  assert cli.main(['pack', '--collection', '系列', '--guide', '-o', str(workspace)]) == 0
  prompt = capsys.readouterr().out
  assert '为合集「系列」写 学习提纲.md' in prompt and '讲了测试视频' in prompt and 'Skipped: 和第一集重复' in prompt
  assert f'../../{asset_folder(workspace, first).name}/' in prompt

  server = fake_model([{'choices': [{'message': {'role': 'assistant', 'content': OVERVIEW}}]}])
  config['base_url'] = f'{server.url}/v1'
  target = summarize_collection(workspace, '系列', config, 'key', status=lambda message: None)
  assert target == workspace / '合集' / '系列' / '合集总结.md' and target.read_text(encoding='utf-8') == OVERVIEW
  sent = server.requests[0]['body']['messages'][-1]['content']
  assert '讲了测试视频' in json.dumps(sent, ensure_ascii=False)

  monkeypatch.setattr('sys.stdin', io.TextIOWrapper(io.BytesIO(('# 学习提纲\n\n' + '要点 ' * 20).encode('utf-8'))))
  assert cli.main(['summarize', '--collection', '系列', '--guide', '--import', '-', '-o', str(workspace)]) == 0
  assert (workspace / '合集' / '系列' / '学习提纲.md').read_text(encoding='utf-8').startswith('# 学习提纲')
  shown = _show(workspace, '系列', capsys)
  assert shown['overview'] and shown['guide']
