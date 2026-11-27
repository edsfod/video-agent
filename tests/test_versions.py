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


def test_each_text_records_whether_it_was_written_afresh_or_from_another_and_keeps_it_when_renamed(tmp_path):
  target = tmp_path / '总结.md'
  body = ''.join(f'- 第 {n} 条要点，写得足够长，长过二十个字，好拿来比较。\n' for n in range(10))
  versions.save(target, '# 旧\n' + body, source='网页 AI')  # before lineage: not known
  data = versions._load(target)
  data['current'].pop('based_on', None)
  data['current'].pop('id', None)
  versions._save(target, data)
  assert versions.listing(target)['current']['origin'] == 'unknown'
  old = versions.listing(target)['current']['id']

  # One written apart shares no line; one written from the old shares most of them.
  fresh = ''.join(f'- 另写的第 {n} 条，和旧稿没有一行相同，也长过二十个字。\n' for n in range(10))
  assert versions.closest(target, fresh) is None
  versions.save(target, fresh, source='Codex', based_on=None)
  edited = body.replace('第 0 条', '第零条')
  found = versions.closest(target, edited)
  assert (found[0], found[1], round(found[2], 1)) == (old, '总结.md', 0.9)
  path, _ = versions.save(target, edited, source='Antigravity', based_on=found[0])

  listed = versions.listing(target)
  by_source = {row['source']: row for row in [listed['current'], *listed['versions']]}
  assert by_source['Codex']['origin'] == 'fresh'
  assert (by_source['Antigravity']['origin'], by_source['Antigravity']['based_on']) == ('revised', old)

  # Made current, it keeps its id and where it came from; written over by a later round, too.
  mine = by_source['Antigravity']['id']
  versions.use(target, path.name)
  current = versions.listing(target)['current']
  assert (current['id'], current['based_on']) == (mine, old)
  versions.overwrite(
    target, '总结.md', edited + '- 再加一条，长过二十个字的内容放在最后。\n', source='Antigravity', based_on=None
  )
  current = versions.listing(target)['current']
  assert (current['id'], current['based_on']) == (mine, old)
  # The lines the template gives every text do not count.
  assert versions.closest(target, body, ignore=body.splitlines()) is None


def test_a_summarys_data_goes_with_its_text_and_lapses_when_the_text_is_changed(tmp_path):
  target = tmp_path / '总结.md'
  versions.save(target, '第一稿\n', data={'units': [1]})
  assert versions.data_of(target)['units'] == [1]
  second, current = versions.save(target, '第二稿\n')  # a version beside the current one, with no data
  assert not current and versions.data_of(second) is None
  versions.save(target, '第三稿\n', make_current=True, data={'units': [3]})
  assert versions.data_of(target)['units'] == [3]
  first = next(v for v in versions.listing(target)['versions'] if v['file'] != second.name)
  assert first['data'] and versions.data_of(tmp_path / first['file'])['units'] == [1]  # the old current kept its data
  versions.use(target, first['file'])
  assert versions.data_of(target)['units'] == [1]
  kept = next(v for v in versions.listing(target)['versions'] if versions.data_of(tmp_path / v['file']))
  assert versions.data_of(tmp_path / kept['file'])['units'] == [3]
  versions.delete(target, kept['file'])
  assert not versions.data_path(tmp_path / kept['file']).exists()
  target.write_text('改过的\n', encoding='utf-8')  # changed by hand: the data no longer counts
  assert versions.data_of(target) is None and versions.listing(target)['current']['data'] is None
