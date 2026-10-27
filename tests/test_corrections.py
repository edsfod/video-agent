"""The cleaned transcript: corrections over a kept original, used by the summary context and `show`."""

import json

from video_agent import cli, corrections
from video_agent.processor import asset_folder


def test_latin_words_match_whole_and_longer_forms_win():
  rows = [(0.0, 1.0, 'react 和 reaction'), (1.0, 2.0, '大模型的 react loop'), (2.0, 3.0, '没有要改的')]
  cleaned, changes = corrections.apply(rows, [('react', 'ReAct'), ('react loop', 'ReAct loop'), ('大模型', 'LLM\\1')])
  assert [text for _, _, text in cleaned] == ['ReAct 和 reaction', 'LLM\\1的 ReAct loop', '没有要改的']
  assert [start for start, _, _ in changes] == [0.0, 1.0]


def test_fix_writes_a_cleaned_transcript_that_the_context_uses(sample_video, tmp_path, capsys):
  workspace = tmp_path / 'work'
  video = str(sample_video)
  assert cli.main(['process', video, '-o', str(workspace), '--frame-interval', '2']) == 0
  asset = asset_folder(workspace, sample_video.resolve())
  original = (asset / 'transcript.srt').read_text(encoding='utf-8')

  capsys.readouterr()
  assert (
    cli.main(['fix', video, '-o', str(workspace), '--replace', '测试视频', '示例视频', '--replace', '没有', '有']) == 0
  )
  out = capsys.readouterr().out
  assert '示例视频' in out and 'not found in the transcript: 没有' in out
  assert (asset / 'transcript.srt').read_text(encoding='utf-8') == original, 'the original stays'
  assert '大家好，今天讲示例视频' in (asset / 'transcript.clean.txt').read_text(encoding='utf-8')
  context = (asset / 'summary-context.md').read_text(encoding='utf-8')
  assert '今天讲示例视频' in context and 'cleaned with 2 corrections' in context
  manifest = json.loads((asset / 'manifest.json').read_text(encoding='utf-8'))
  assert manifest['transcript']['clean'] == 'transcript.clean.srt'

  assert cli.main(['show', video, '-o', str(workspace)]) == 0
  shown = json.loads(capsys.readouterr().out)
  assert shown['transcript'].endswith('transcript.clean.txt') and shown['transcript_original'].endswith(
    'transcript.txt'
  )
  assert shown['corrections'] == [['测试视频', '示例视频'], ['没有', '有']]

  # Processing again keeps the corrections; taking them back returns to the original.
  assert cli.main(['process', video, '-o', str(workspace), '--frame-interval', '2']) == 0
  assert (asset / 'transcript.clean.txt').is_file()
  assert cli.main(['fix', video, '-o', str(workspace), '--remove', '测试视频', '--remove', '没有']) == 0
  assert not (asset / 'transcript.clean.txt').exists() and not (asset / 'corrections.json').exists()
  assert '今天讲测试视频' in (asset / 'summary-context.md').read_text(encoding='utf-8')


def test_fix_needs_a_processed_video(sample_video, tmp_path, capsys):
  assert cli.main(['fix', str(sample_video), '-o', str(tmp_path), '--replace', 'a', 'b']) == 1
  assert 'run process' in capsys.readouterr().out
