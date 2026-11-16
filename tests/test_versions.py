"""Versions kept for an Agent before it runs (`versions --keep`, then `--settle` when it has finished)."""

from video_agent import versions


def test_a_copy_kept_for_an_agent_goes_unless_the_agent_wrote_over_the_current_text(tmp_path):
  target = tmp_path / '总结.md'
  versions.save(target, 'old\n', source='网页 AI', note='命题分析', pictures='1')
  before = versions.listing(target)['current']

  # The Agent saves its text through the import: the current text keeps its record, and the copy goes.
  versions.keep(target, source='Antigravity')
  assert versions.listing(target)['current'] == before, 'keeping a copy leaves the current record alone'
  versions.save(target, 'new\n', source='Antigravity gemini')
  versions.settle(target)
  found = versions.listing(target)
  assert found['current'] == before
  assert [
    (version['source'], target.with_name(version['file']).read_text(encoding='utf-8')) for version in found['versions']
  ] == [('Antigravity gemini', 'new\n')]

  # An Agent that writes the file itself: its text is recorded as its own, and the old one stays as a version.
  versions.keep(target, source='Codex')
  target.write_text('by hand\n', encoding='utf-8')
  versions.settle(target)
  found = versions.listing(target)
  assert found['current']['source'] == 'Codex'
  assert {version['source']: version['note'] for version in found['versions']} == {
    'Antigravity gemini': '',
    '网页 AI': '命题分析',
  }

  # Nothing done: the copy goes and nothing else changes.
  versions.keep(target, source='Claude Code')
  versions.settle(target)
  assert versions.listing(target) == found
