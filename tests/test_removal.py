"""Deleting videos from the workspace: folders, collections, and the file only when this program downloaded it."""

import json

from video_agent import cli, collection, processor


def _processed(workspace, video, name=None):
  """A processing folder, enough for deleting: summaries, and for one under another name a manifest naming the video
  (a full manifest would have the collection rebuild its transcript)."""
  folder = workspace / name if name else processor.asset_folder(workspace, video.resolve())
  folder.mkdir(parents=True)
  if name:
    (folder / 'manifest.json').write_text(json.dumps({'source_video': str(video)}), encoding='utf-8')
  (folder / '总结.md').write_text('# 总结\n', encoding='utf-8')
  (folder / '总结 (2026-11-16 10-00-00).md').write_text('# 旧版本\n', encoding='utf-8')
  return folder


def test_a_downloaded_video_goes_whole_and_a_local_one_keeps_its_file(tmp_path, capsys):
  workspace = tmp_path / 'work'
  got = workspace / '下载' / 'talk [BV1].mp4'
  got.parent.mkdir(parents=True)
  got.write_bytes(b'video')
  subtitles = got.with_name('talk [BV1].ai-zh.srt')
  subtitles.write_text('1\n', encoding='utf-8')
  other = got.with_name('talk [BV1] part 2.mp4')  # starts like it, is another video
  other.write_bytes(b'video')
  mine = tmp_path / 'my videos' / 'lecture.mp4'
  mine.parent.mkdir()
  mine.write_bytes(b'video')
  first = _processed(workspace, got)
  older = _processed(workspace, got, 'talk-BV1-old-name')  # made under an earlier folder name
  local = _processed(workspace, mine)
  collection.create(workspace, '课程', [str(got), str(mine)])

  assert cli.main(['delete', str(got), str(mine), '-o', str(workspace), '--json']) == 0
  done = json.loads(capsys.readouterr().out)
  assert [entry['video_kept'] for entry in done] == [False, True]
  assert sorted(done[0]['folders']) == sorted([str(first), str(older)]) and done[0]['collections'] == ['课程']
  assert not got.exists() and not subtitles.exists() and other.exists(), 'the file and its subtitles, nothing else'
  assert mine.exists() and not local.exists(), "the user's own file stays, its folder goes"
  assert not first.exists() and not older.exists()
  assert collection.load(workspace, '课程')['videos'] == []


def test_a_followed_collections_download_folder_counts_as_downloaded(tmp_path):
  from video_agent import removal

  workspace = tmp_path / 'work'
  folder = tmp_path / 'course videos'
  folder.mkdir()
  collection.create(workspace, '跟进的', [])
  collection.follow(workspace, '跟进的', 'https://example.com/list', folder)
  assert removal.downloaded(workspace, folder / 'a.mp4')
  assert not removal.downloaded(workspace, tmp_path / 'a.mp4')
