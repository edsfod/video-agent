"""Subtitle parsing, times, process, frame, download with a fake yt-dlp, and summarize settings."""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from video_agent import cli, contract, download, layout, media, processor, settings, transcript
from video_agent.processor import asset_folder

VTT = 'WEBVTT\n\nNOTE skipped\n\n00:01.000 --> 00:02.500\nfirst\n\n1\n00:00:03.000 --> 00:00:04.000\nsecond\nline\n'


def test_parse_vtt_and_srt_round_trip():
  rows = transcript.parse(VTT)
  assert rows == [(1.0, 2.5, 'first'), (3.0, 4.0, 'second\nline')]
  assert transcript.parse(transcript.format_srt(rows)) == rows
  assert transcript.format_text(rows) == '[00:00:01] first\n[00:00:03] second line\n'


@pytest.mark.parametrize('value, seconds', [('70', 70), ('1:10', 70), ('00:01:10', 70), ('1:02:03.5', 3723.5)])
def test_parse_clock(value, seconds):
  assert media.parse_clock(value) == seconds


@pytest.mark.parametrize('value', ['', 'abc', '1:2:3:4', '-5'])
def test_parse_clock_rejects(value):
  with pytest.raises(ValueError):
    media.parse_clock(value)


def test_process_uses_sidecar_and_frame_saves_extra(sample_video, tmp_path, capsys):
  workspace = tmp_path / 'work'
  assert cli.main(['process', str(sample_video), '-o', str(workspace), '--frame-interval', '2']) == 0
  asset = asset_folder(workspace, sample_video.resolve())
  manifest = json.loads((asset / 'manifest.json').read_text(encoding='utf-8'))
  assert manifest['transcript']['source'] == 'sidecar:sample clip [test].srt'
  assert manifest['transcript']['segments'] == 2
  assert manifest['slide_extraction']['enabled'] is False
  assert 2 <= len(manifest['representative_frames']) <= 36
  context = (asset / 'summary-context.md').read_text(encoding='utf-8')
  assert '[00:00:03] 我们看看这张图表' in context
  assert sample_video.read_bytes()  # the source is left in place

  capsys.readouterr()
  assert cli.main(['frame', str(sample_video), '0:05', '9', '-o', str(workspace)]) == 1
  out = capsys.readouterr().out
  assert (asset / 'frames' / 'extra' / 'frame-00-00-05.jpg').is_file()
  assert '9s: ERROR' in out


def test_a_processed_video_is_used_as_it_is_unless_forced_or_asked_for_more(sample_video, tmp_path, capsys):
  workspace = tmp_path / 'work'
  first = ['process', str(sample_video), '-o', str(workspace), '--frame-interval', '2', '--json']
  assert cli.main(first) == 0
  asset = asset_folder(workspace, sample_video.resolve())
  run = json.loads((asset / 'manifest.json').read_text(encoding='utf-8'))['representative_frame_run']
  capsys.readouterr()
  assert cli.main(first) == 0
  captured = capsys.readouterr()
  assert json.loads(captured.out)['reused'] is True and 'processed already' in captured.err
  assert json.loads((asset / 'manifest.json').read_text(encoding='utf-8'))['representative_frame_run'] == run
  assert cli.main([*first, '--force']) == 0
  assert 'reused' not in json.loads(capsys.readouterr().out)
  assert cli.main(['process', str(sample_video), '-o', str(workspace), '--frame-interval', '3', '--json']) == 0
  assert 'reused' not in json.loads(capsys.readouterr().out), 'other frame settings'


def test_regions_given_by_hand_and_the_layout_check():
  assert layout.from_region('4,4,1912,1072', 1920, 1080).kind == 'screen', 'only the edges trimmed'
  assert layout.from_region('0,0,1280,1080', 1920, 1080).kind == 'split'

  camera = layout.Layout('camera', 640, 360, None)
  assert 'layout was probably read wrong' in processor.layout_warning(camera, 0, 3600, False)
  assert processor.layout_warning(camera, 0, 120, False) is None, 'too short to tell'
  assert processor.layout_warning(camera, 0, 3600, True) is None, 'a region given by hand'


def test_share_tracking_is_dropped_from_links():
  assert download.clean_url('https://www.bilibili.com/video/BV1x/?p=2&vd_source=ab&spm_id_from=333.1') == (
    'https://www.bilibili.com/video/BV1x/?p=2'
  )
  assert download.clean_url('https://youtu.be/abc?si=XYZ&t=90&utm_source=x') == 'https://youtu.be/abc?t=90'
  assert download.clean_url(' https://example.com/a ') == 'https://example.com/a'


def test_a_chosen_subtitle_file_becomes_the_transcript_whatever_its_name(sample_video, tmp_path):
  bare = tmp_path / 'bare.mp4'
  bare.write_bytes(sample_video.read_bytes())
  chosen = tmp_path / 'from the teacher.vtt'
  chosen.write_text('WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n老师给的字幕\n', encoding='utf-8')
  workspace = tmp_path / 'work'
  assert cli.main(['process', str(bare), '-o', str(workspace), '--subtitles', str(chosen)]) == 0
  asset = asset_folder(workspace, bare.resolve())
  manifest = json.loads((asset / 'manifest.json').read_text(encoding='utf-8'))
  assert manifest['transcript']['source'] == 'file:from the teacher.vtt'
  assert '老师给的字幕' in (asset / 'summary-context.md').read_text(encoding='utf-8')
  with pytest.raises(SystemExit):  # the parser reports it: --subtitles belongs to one video
    cli.main(['process', str(bare), str(sample_video), '-o', str(workspace), '--subtitles', str(chosen)])


def _slide_image(video, second, path):
  path.parent.mkdir(parents=True, exist_ok=True)
  subprocess.run(
    [media.tool('ffmpeg'), '-v', 'error', '-y', '-ss', str(second), '-i', str(video), '-frames:v', '1', str(path)],
    check=True,
  )


def test_slides_autoslides_keeps_beside_a_screen_recording_are_taken_with_their_times(sample_video, tmp_path):
  video = tmp_path / 'screen_第1周.mp4'
  video.write_bytes(sample_video.read_bytes())
  folder = tmp_path / 'slides_第1周'
  _slide_image(sample_video, 1, folder / 'Slide_001.png')
  _slide_image(sample_video, 6, folder / 'Slide_002.png')
  events = [{'id': 'a', 'changeAt': 0.0, 'initialFile': 'Slide_001.png'}, {'id': 'b', 'changeAt': 4.5}]
  resolutions = {
    'a': {'file': 'Slide_001.png', 'state': 'canonical'},
    'b': {'file': 'Slide_002.png', 'state': 'canonical'},
  }
  (folder / 'timeline.json').write_text(json.dumps({'events': events, 'resolutions': resolutions}), encoding='utf-8')
  workspace = tmp_path / 'work'
  assert cli.main(['process', str(video), '-o', str(workspace)]) == 1  # no subtitles: the slides are still taken
  asset = asset_folder(workspace, video.resolve())
  taken = json.loads((asset / 'manifest.json').read_text(encoding='utf-8'))['slide_extraction']
  assert taken['imported'] == str(folder.resolve())
  assert [(item['time_s'], Path(item['path']).name) for item in taken['slides']] == [
    (0.0, 'slide-001.png'),
    (4.5, 'slide-002.png'),
  ]
  assert all((asset / item['path']).is_file() for item in taken['slides'])


def test_a_chosen_slide_folder_without_times_is_placed_by_the_screen_pages(sample_video, tmp_path):
  folder = tmp_path / '课件'
  _slide_image(sample_video, 6, folder / 'page.jpg')
  workspace = tmp_path / 'work'
  assert cli.main(['process', str(sample_video), '-o', str(workspace), '--slides', str(folder)]) == 0
  asset = asset_folder(workspace, sample_video.resolve())
  manifest = json.loads((asset / 'manifest.json').read_text(encoding='utf-8'))
  [slide] = manifest['slide_extraction']['slides']
  assert slide['time_s'] is not None and slide['time_s'] >= 3  # the second half of the sample, where it was taken
  assert '▶ slide from' in (asset / 'summary-context.md').read_text(encoding='utf-8')


def test_process_without_subtitles_asks_for_consent(sample_video, tmp_path, capsys):
  bare = tmp_path / 'bare.mp4'
  bare.write_bytes(sample_video.read_bytes())
  assert cli.main(['process', str(bare), '-o', str(tmp_path / 'work')]) == 1
  assert '--allow-remote-asr' in capsys.readouterr().out


def test_allow_remote_asr_needs_bcut(sample_video, tmp_path):
  with pytest.raises(SystemExit) as stopped:
    cli.main(['process', str(sample_video), '--allow-remote-asr', '-o', str(tmp_path)])
  assert stopped.value.code == 2


FAKE_YT_DLP = textwrap.dedent("""
  import json, sys
  from pathlib import Path
  args = sys.argv[1:]
  url = args[-1]
  if '--dump-single-json' in args:
    if 'list' in url:
      print(json.dumps({'_type': 'playlist', 'id': 'x', 'title': '合集·系列', 'entries': [{'title': 'one'}, {}]}))
    else:
      print(json.dumps({'_type': 'video', 'id': 'x'}))
    sys.exit(0)
  if 'fail' in url or ('subtitle-error' in url and '--write-subs' in args):
    sys.exit(1)
  template = args[args.index('--output') + 1]
  # A list holds the ids in ids.txt beside this script (one video, abc, without it); an archive skips those it lists.
  listed = Path(__file__).with_name('ids.txt')
  ids = listed.read_text().split() if 'list' in url and listed.is_file() else ['abc']
  archive = Path(args[args.index('--download-archive') + 1]) if '--download-archive' in args else None
  done = archive.read_text().split('\\n') if archive and archive.is_file() else []
  for vid in ids:
    if f'fake {vid}' in done:
      continue
    title = 'Clip' if vid == 'abc' else f'Clip {vid}'
    path = Path(template.replace('%(title)s', title).replace('%(id)s', vid).replace('%(ext)s', 'mp4'))
    path.write_bytes(b'video')
    if '--write-subs' in args:
      path.with_suffix('.ai-zh.srt').write_text('1\\n00:00:01,000 --> 00:00:02,000\\nhi\\n', encoding='utf-8')
    print(path)
    if archive:
      with archive.open('a') as file:
        file.write(f'fake {vid}\\n')
""")


@pytest.fixture
def fake_yt_dlp(tmp_path, monkeypatch):
  script = tmp_path / 'fake_yt_dlp.py'
  script.write_text(FAKE_YT_DLP, encoding='utf-8')
  monkeypatch.setattr(download, 'executable', lambda explicit=None: [sys.executable, str(script)])


def test_download_returns_paths_and_refuses_playlists(fake_yt_dlp, tmp_path):
  messages, lists = [], []
  paths, failed = download.download_urls(
    ['https://example.com/video', 'https://example.com/list', 'https://example.com/fail'],
    tmp_path / 'downloads',
    status=messages.append,
    found_list=lists.append,
  )
  assert [path.name for path in paths] == ['Clip [abc].mp4']
  assert failed == 2
  assert any('pass --playlist' in message for message in messages)
  assert lists == [{'url': 'https://example.com/list', 'title': '合集·系列', 'count': 2, 'titles': ['one']}]

  paths, failed = download.download_urls(['https://example.com/list'], tmp_path / 'more', playlist=True, status=print)
  assert len(paths) == 1 and failed == 0


def test_download_saves_subtitles_and_passes_cookies(fake_yt_dlp, tmp_path, monkeypatch):
  seen = []
  real_popen = download.subprocess.Popen

  def spy(command, **options):
    seen.append(command)
    return real_popen(command, **options)

  monkeypatch.setattr(download.subprocess, 'Popen', spy)
  cookies = tmp_path / 'cookies.txt'
  cookies.write_text('# Netscape HTTP Cookie File\n', encoding='utf-8')
  _, failed = download.download_urls(
    ['https://example.com/video'], tmp_path / 'out', cookies_path=cookies, status=lambda message: None
  )
  assert failed == 0 and (tmp_path / 'out' / 'Clip [abc].ai-zh.srt').is_file()
  command = next(command for command in seen if '--no-simulate' in command)  # run() goes through Popen as well
  assert command[command.index('--sub-langs') + 1] == 'all,-danmaku,-live_chat'
  assert command[command.index('--cookies') + 1] == str(cookies.resolve())
  fixes = [command[index + 2 : index + 4] for index, arg in enumerate(command) if arg == '--replace-in-metadata']
  assert fixes == [['[/\\\\]', '_']]  # a regex for / or one backslash

  with pytest.raises(download.DownloadError):
    download.download_urls(['https://example.com/video'], tmp_path / 'out', cookies_path=tmp_path / 'missing.txt')


def test_download_retries_without_subtitles(fake_yt_dlp, tmp_path):
  messages = []
  paths, failed = download.download_urls(
    ['https://example.com/subtitle-error'], tmp_path / 'out', status=messages.append
  )
  assert [path.name for path in paths] == ['Clip [abc].mp4'] and failed == 0
  assert any('retrying without subtitles' in message for message in messages)
  assert not list((tmp_path / 'out').glob('*.srt'))

  download.download_urls(['https://example.com/video'], tmp_path / 'bare', subtitles=False, status=print)
  assert not list((tmp_path / 'bare').glob('*.srt'))


def test_sidecar_prefers_human_chinese_tracks_and_skips_other_videos(tmp_path):
  video = tmp_path / 'talk [BV1xx].mp4'
  video.write_bytes(b'')

  def subtitle(name, text):
    (tmp_path / name).write_text(f'1\n00:00:01,000 --> 00:00:02,000\n{text}\n', encoding='utf-8')

  subtitle('talk [BV1xx].part2.srt', 'other video')
  assert transcript.sidecar(video) is None
  subtitle('talk [BV1xx].ai-zh.srt', 'ai')
  subtitle('talk [BV1xx].en-US.srt', 'english')
  assert transcript.sidecar(video)[1] == 'sidecar:talk [BV1xx].en-US.srt'
  subtitle('talk [BV1xx].zh-CN.srt', 'chinese')
  assert transcript.sidecar(video) == ([(1.0, 2.0, 'chinese')], 'sidecar:talk [BV1xx].zh-CN.srt')
  subtitle('talk [BV1xx].srt', 'plain')
  assert transcript.sidecar(video)[1] == 'sidecar:talk [BV1xx].srt'


@pytest.fixture
def isolated_settings(tmp_path, monkeypatch):
  monkeypatch.setenv('APPDATA', str(tmp_path / 'appdata'))
  monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
  monkeypatch.delenv('OPENAI_API_KEY', raising=False)
  monkeypatch.setattr(settings, '_target', lambda provider: f'video-agent-test:{provider}')
  yield
  for provider in settings.PROVIDERS:
    settings.delete_key(provider)


def test_config_saves_settings_and_key(isolated_settings, monkeypatch, capsys):
  monkeypatch.setattr(sys, 'stdin', type('In', (), {'isatty': lambda self: False, 'readline': lambda self: 'k-1\n'})())
  assert cli.main(['config', '--provider', 'openai', '--model', 'qwen', '--base-url', 'http://h/v1/', '--set-key']) == 0
  out = capsys.readouterr().out
  assert 'API key:  Credential Manager' in out
  assert settings.resolve() == {'provider': 'openai', 'model': 'qwen', 'base_url': 'http://h/v1'}
  assert settings.get_key('openai') == 'k-1'
  assert 'k-1' not in Path(settings.settings_path()).read_text(encoding='utf-8')
  assert cli.main(['config', '--delete-key']) == 0
  assert settings.get_key('openai') is None


def test_environment_key_is_the_fallback(isolated_settings, monkeypatch):
  monkeypatch.setenv('ANTHROPIC_API_KEY', 'from-env')
  assert settings.get_key('anthropic') == 'from-env'
  assert settings.key_source('anthropic') == 'environment variable ANTHROPIC_API_KEY'


def test_template_is_packaged(capsys):
  assert cli.main(['template']) == 0
  out = capsys.readouterr().out
  assert out.startswith('# Writing a video summary') and '## 视频总结 `总结.md`' in out


def test_process_json_and_show(sample_video, tmp_path, capsys):
  workspace = tmp_path / 'work'
  assert cli.main(['show', str(sample_video), '-o', str(workspace)]) == 0
  before = json.loads(capsys.readouterr().out)
  assert before['processed'] is False and before['summary'] is None

  assert cli.main(['process', str(sample_video), '-o', str(workspace), '--json']) == 0
  captured = capsys.readouterr()
  result = json.loads(captured.out)
  assert result['rows'] == 2 and Path(result['asset']).is_dir()
  assert 'evidence saved' in captured.err

  assert cli.main(['show', str(sample_video), '-o', str(workspace)]) == 0
  after = json.loads(capsys.readouterr().out)
  assert after['processed'] and after['folder'] == result['asset']
  assert after['manifest']['transcript']['segments'] == 2
  assert after['transcript'].endswith('transcript.txt')


def test_config_json(isolated_settings, capsys):
  assert cli.main(['config', '--json']) == 0
  shown = json.loads(capsys.readouterr().out)
  assert shown['provider'] == 'anthropic' and shown['key'] is None


def test_frames_closer_than_a_second_are_merged(tmp_path):
  from video_agent.processor import _unique

  def frame(name, second):
    path = tmp_path / name
    path.write_bytes(name.encode())
    return {'time_s': second, 'path': path}

  kept = _unique([frame('a', 27.0), frame('b', 27.4), frame('c', 28.5), frame('d', 60.0)])
  assert [item['time_s'] for item in kept] == [27.0, 28.5, 60.0]


def test_reprocessing_keeps_the_original_transcript_source(sample_video, tmp_path):
  workspace = tmp_path / 'work'
  for _ in range(2):
    assert cli.main(['process', str(sample_video), '-o', str(workspace)]) == 0
  manifest = json.loads((asset_folder(workspace, sample_video.resolve()) / 'manifest.json').read_text(encoding='utf-8'))
  assert manifest['transcript']['source'] == 'sidecar:sample clip [test].srt'


def test_help_survives_a_non_utf8_pipe():
  import subprocess

  env = {**__import__('os').environ, 'PYTHONIOENCODING': 'cp1252', 'PYTHONUTF8': '0'}
  result = subprocess.run([sys.executable, '-m', 'video_agent', '--help'], capture_output=True, env=env, check=False)
  assert result.returncode == 0, result.stderr.decode('utf-8', 'replace')
  assert '总结.md' in result.stdout.decode('utf-8')


@pytest.fixture
def embedded_mkv(sample_video, tmp_path):
  """The sample with its subtitles muxed in as a Chinese-tagged stream and no sidecar file."""
  import subprocess

  target = tmp_path / 'embedded.mkv'
  subprocess.run(
    [
      media.tool('ffmpeg'),
      '-y',
      '-hide_banner',
      '-loglevel',
      'error',
      '-i',
      str(sample_video),
      '-i',
      str(sample_video.with_suffix('.srt')),
      '-map',
      '0',
      '-map',
      '1',
      '-c',
      'copy',
      '-c:s',
      'srt',
      '-metadata:s:s:0',
      'language=chi',
      str(target),
    ],
    check=True,
  )
  return target


def _summary(info):
  streams = [
    (s['index'], s['codec_type'], s['codec_name'], (s.get('tags') or {}).get('language')) for s in info['streams']
  ]
  return round(float(info['format']['duration']), 1), streams


def test_ffmpeg_probe_matches_ffprobe(sample_video, embedded_mkv, monkeypatch):
  import shutil

  if not shutil.which('ffprobe'):
    pytest.skip('ffprobe not installed')
  for video in (sample_video, embedded_mkv):
    _, with_ffprobe = media.probe(video)
    monkeypatch.setattr(media, 'tool', lambda name, real=media.tool: None if name == 'ffprobe' else real(name))
    _, without = media.probe(video)
    monkeypatch.undo()
    duration, streams = _summary(with_ffprobe)
    other_duration, other_streams = _summary(without)
    assert abs(duration - other_duration) < 0.1
    assert [s[:3] for s in streams] == [s[:3] for s in other_streams]
    assert [s[3] for s in streams] == [s[3] for s in other_streams]


def test_works_without_ffmpeg_on_path(embedded_mkv, tmp_path, monkeypatch):
  monkeypatch.setattr(media.shutil, 'which', lambda name: None)
  assert media.tool('ffprobe') is None
  assert 'imageio_ffmpeg' in media.tool('ffmpeg')
  workspace = tmp_path / 'work'
  assert cli.main(['process', str(embedded_mkv), '-o', str(workspace), '--frame-interval', '2']) == 0
  manifest = json.loads((asset_folder(workspace, embedded_mkv.resolve()) / 'manifest.json').read_text(encoding='utf-8'))
  assert manifest['transcript']['source'] == 'embedded:chi'
  assert manifest['transcript']['segments'] == 2
  assert manifest['representative_frames']


def test_bundled_yt_dlp_entry(capsys):
  with pytest.raises(SystemExit) as stopped:
    cli.main(['_yt-dlp', '--version'])
  assert stopped.value.code in (0, None)
  assert capsys.readouterr().out.strip()[:4].isdigit()


def test_download_tells_yt_dlp_where_ffmpeg_is(fake_yt_dlp, tmp_path, monkeypatch):
  seen = []
  real_run = download.subprocess.run

  def spy(command, **options):
    seen.append(command)
    return real_run(command, **options)

  monkeypatch.setattr(download.subprocess, 'run', spy)
  download.download_urls(['https://example.com/video'], tmp_path / 'out', status=lambda message: None)
  command = seen[0]
  assert command[command.index('--ffmpeg-location') + 1] == media.tool('ffmpeg')


@pytest.mark.parametrize('bundled', [False, True])
def test_no_scene_changes_is_not_an_error(tmp_path, monkeypatch, bundled):
  still = tmp_path / 'still.mp4'
  command = [
    media.tool('ffmpeg'),
    '-y',
    '-v',
    'error',
    '-filter_complex',
    'color=gray:size=160x120:rate=5:d=3[v]',
    '-map',
    '[v]',
  ]
  subprocess.run([*command, '-pix_fmt', 'yuv420p', str(still)], check=True)
  if bundled:
    monkeypatch.setattr(media.shutil, 'which', lambda name: None)
  periodic, scenes = media.sample_frames(still, tmp_path / 'samples', 60, 0.35)
  assert [item['time_s'] for item in periodic] == [0.0]
  assert [item['time_s'] for item in scenes] == [0.0]  # frame 0 only, which keeps the output from being empty


def _bump_script():
  import importlib.util

  root = Path(__file__).resolve().parents[1]
  spec = importlib.util.spec_from_file_location('bump_version', root / 'scripts' / 'bump_version.py')
  script = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(script)
  return script


def test_versions_match():
  from video_agent import __version__

  script = _bump_script()
  python = script.python(__version__)
  root = Path(__file__).resolve().parents[1]
  for name in ('plugin.json', '.claude-plugin/plugin.json', 'gui/package.json'):
    assert json.loads((root / name).read_text(encoding='utf-8'))['version'] == __version__, name
  lock = json.loads((root / 'gui/package-lock.json').read_text(encoding='utf-8'))
  assert lock['version'] == lock['packages']['']['version'] == __version__
  assert f'name = "video-agent"\nversion = "{python}"\n' in (root / 'uv.lock').read_text(encoding='utf-8')
  assert f'\nversion = "{python}"\n' in (root / 'pyproject.toml').read_text(encoding='utf-8')
  wheel = script.wheel(__version__)
  assert (root / 'skills/video-agent/SKILL.md').read_text(encoding='utf-8').count(wheel) == 2
  # During a pre-release README.md keeps the last full release's link.
  assert (wheel in (root / 'README.md').read_text(encoding='utf-8')) != script.prerelease(__version__)


def test_prerelease_versions_are_spelled_for_each_ecosystem():
  script = _bump_script()
  assert [script.python(v) for v in ('0.9.2', '0.9.2-beta', '0.9.2-beta.2', '1.0.0-rc.1', '1.0.0-alpha')] == [
    '0.9.2',
    '0.9.2b0',
    '0.9.2b2',
    '1.0.0rc1',
    '1.0.0a0',
  ]
  assert script.wheel('0.9.2-beta') == 'releases/download/v0.9.2-beta/video_agent-0.9.2b0-py3-none-any.whl'


def test_bump_version_changes_every_file_or_none(tmp_path):
  import shutil

  root = Path(__file__).resolve().parents[1]
  script = _bump_script()
  for name in script.CHANGES:
    (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root / name, tmp_path / name)
  if script.prerelease(script.current(tmp_path)):  # start from a full release, as a beta leaves README.md alone
    script.bump('9.9.8', tmp_path)
  old = script.current(tmp_path)
  start = {name: (tmp_path / name).read_text(encoding='utf-8') for name in script.CHANGES}
  readme = start['README.md']
  (tmp_path / 'README.md').write_text(readme.replace(f'v{old}/', 'v0.0.1/'), encoding='utf-8', newline='\n')
  with pytest.raises(ValueError, match='README.md'):
    script.bump('9.9.9', tmp_path)
  assert script.current(tmp_path) == old, 'nothing is written when one file does not match'
  (tmp_path / 'README.md').write_text(readme, encoding='utf-8', newline='\n')
  assert script.bump('9.9.9', tmp_path) == (old, list(script.CHANGES))
  for name in script.CHANGES:
    assert (tmp_path / name).read_text(encoding='utf-8').replace('9.9.9', old) == start[name], name
  with pytest.raises(ValueError, match='not a version'):
    script.bump('1.0', tmp_path)
  # A pre-release, then its full release: Python's spelling in its files, README.md left until the full one.
  text = lambda name: (tmp_path / name).read_text(encoding='utf-8')
  readme = text('README.md')
  script.bump('9.9.10-beta', tmp_path)
  assert script.current(tmp_path) == '9.9.10-beta'
  assert '\nversion = "9.9.10b0"\n' in text('pyproject.toml')
  assert 'name = "video-agent"\nversion = "9.9.10b0"\n' in text('uv.lock')
  assert text('skills/video-agent/SKILL.md').count('v9.9.10-beta/video_agent-9.9.10b0-py3-none-any.whl') == 2
  assert json.loads(text('gui/package.json'))['version'] == '9.9.10-beta'
  assert text('README.md') == readme
  script.bump('9.9.10', tmp_path)
  assert 'v9.9.10/video_agent-9.9.10-py3-none-any.whl' in text('README.md')
  assert '\nversion = "9.9.10"\n' in text('pyproject.toml')


def test_video_lock_is_released_when_its_process_is_killed(tmp_path):
  from video_agent import files

  script = (
    'import sys, time\n'
    'from video_agent import files\n'
    'with files.video_lock(sys.argv[1], "test"):\n'
    '  print("held", flush=True)\n'
    '  time.sleep(60)\n'
  )
  holder = subprocess.Popen(
    [sys.executable, '-c', script, str(tmp_path)],
    stdout=subprocess.PIPE,
    text=True,
  )
  try:
    assert holder.stdout.readline().strip() == 'held'
    with pytest.raises(files.BusyError), files.video_lock(tmp_path, 'test'):
      pass
  finally:
    holder.kill()
    holder.wait()
  with files.video_lock(tmp_path, 'test'):
    pass


def test_a_playlist_download_can_fill_a_collection(fake_yt_dlp, tmp_path):
  from video_agent import collection

  workspace = tmp_path / 'work'
  args = ['download', 'https://example.com/list', '--playlist', '-o', str(tmp_path / 'dl'), '--collection', '系列']
  assert cli.main([*args, '--workspace', str(workspace)]) == 0
  assert [Path(video).name for video in collection.load(workspace, '系列')['videos']] == ['Clip [abc].mp4']


def test_a_list_found_without_playlist_is_reported_as_json(fake_yt_dlp, tmp_path, capsys):
  assert cli.main(['download', 'https://example.com/list', '-o', str(tmp_path / 'dl'), '--json']) == 1
  lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith('{')]
  assert lines == [
    {'playlist': {'url': 'https://example.com/list', 'title': '合集·系列', 'count': 2, 'titles': ['one']}}
  ]


def test_a_followed_list_downloads_only_its_new_videos(fake_yt_dlp, tmp_path, capsys):
  from video_agent import collection

  ids = tmp_path / 'ids.txt'
  ids.write_text('abc')
  workspace, folder = tmp_path / 'work', tmp_path / 'dl'
  url = 'https://example.com/list'
  args = ['download', url, '--playlist', '--collection', '连载', '--follow', '-o', str(folder)]
  assert cli.main([*args, '--workspace', str(workspace)]) == 0
  source = collection.load(workspace, '连载')['source']
  assert (source['url'], source['folder'], source['auto'], source['new']) == (url, str(folder.resolve()), False, 1)

  ids.write_text('abc\ndef')
  capsys.readouterr()
  assert cli.main(['collection', 'update', '连载', '-o', str(workspace), '--json']) == 0
  out = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
  assert [Path(item['path']).name for item in out if 'path' in item] == ['Clip def [def].mp4']
  data = collection.load(workspace, '连载')
  assert [Path(video).name for video in data['videos']] == ['Clip [abc].mp4', 'Clip def [def].mp4']
  assert data['source']['new'] == 1 and data['source']['checked']

  assert cli.main(['collection', 'update', '连载', '-o', str(workspace)]) == 0
  assert collection.load(workspace, '连载')['source']['new'] == 0

  assert cli.main(['collection', 'follow', '连载', '--auto', '-o', str(workspace)]) == 0
  assert collection.load(workspace, '连载')['source']['auto'] is True
  assert cli.main(['collection', 'unfollow', '连载', '-o', str(workspace)]) == 0
  assert 'source' not in collection.load(workspace, '连载')
  assert not collection.archive(workspace, '连载').exists()
  assert cli.main(['collection', 'update', '连载', '-o', str(workspace)]) == 1


def test_an_existing_collection_can_follow_its_list_later(fake_yt_dlp, tmp_path, capsys):
  from video_agent import collection

  (tmp_path / 'ids.txt').write_text('abc')
  workspace, folder = tmp_path / 'work', tmp_path / 'dl'
  url = 'https://example.com/list'
  assert (
    cli.main(['download', url, '--playlist', '--collection', '旧', '-o', str(folder), '--workspace', str(workspace)])
    == 0
  )
  assert cli.main(['collection', 'follow', '旧', url, '--folder', str(folder), '-o', str(workspace)]) == 0
  (tmp_path / 'ids.txt').write_text('abc\nxyz')
  capsys.readouterr()
  assert cli.main(['collection', 'update', '旧', '-o', str(workspace), '--json']) == 0
  # The first update has no archive yet, so yt-dlp meets abc again; it stays where it was, xyz comes after it.
  names = [Path(video).name for video in collection.load(workspace, '旧')['videos']]
  assert names == ['Clip [abc].mp4', 'Clip xyz [xyz].mp4']
  # abc was in the folder already: the window does not process it again after the download (user report, 2026-10-28).
  out = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
  assert [(Path(item['path']).name, item['new']) for item in out if 'path' in item] == [
    ('Clip [abc].mp4', False),
    ('Clip xyz [xyz].mp4', True),
  ]


def test_tools_reports_each_program_or_null(monkeypatch, capsys):
  from video_agent import slide_extractor

  def missing(explicit=None):
    raise slide_extractor.SlideExtractorError('not found')

  monkeypatch.setattr(slide_extractor, 'find_extractor', missing)
  assert cli.main(['tools', '--json']) == 0
  found = json.loads(capsys.readouterr().out)
  assert set(found) == {'json_version', 'ffmpeg', 'ffprobe', 'yt_dlp', 'slide_extractor'}
  assert found['json_version'] == contract.JSON_VERSION
  assert found['ffmpeg'] and found['slide_extractor'] is None


def test_a_folder_keeps_the_chinese_name_and_an_old_one_is_renamed_with_its_links(tmp_path):
  from video_agent import processor

  video = (tmp_path / '软件仓库管理 [BV1].mp4').resolve()
  workspace = tmp_path / 'work'
  identity = processor.asset_folder(tmp_path / 'empty', video).name.rsplit('-', 1)[1]
  old = workspace / f'BV1-{identity}'  # what 0.8.3 named it: the Chinese dropped
  old.mkdir(parents=True)
  (old / '总结.md').write_text('# 总结\n', encoding='utf-8')
  overview = workspace / '合集' / '课' / '合集总结.md'
  overview.parent.mkdir(parents=True)
  overview.write_text(f'[总结](../../{old.name}/总结.md)\n', encoding='utf-8')

  folder = processor.asset_folder(workspace, video)
  assert folder.name == f'软件仓库管理-BV1-{identity}' and (folder / '总结.md').is_file() and not old.exists()
  assert overview.read_text(encoding='utf-8') == f'[总结](../../{folder.name}/总结.md)\n'
  assert processor.asset_folder(workspace, video) == folder


def _has_svtav1():
  command = [media.tool('ffmpeg'), '-hide_banner', '-encoders']
  encoders = subprocess.run(command, capture_output=True, text=True, check=False).stdout
  return 'libsvtav1' in encoders


# CI's cli job runs on the FFmpeg the installer ships, which has SVT-AV1; on a cold cache it falls back to choco's,
# which has not.
@pytest.mark.skipif(not _has_svtav1(), reason='this FFmpeg has no SVT-AV1 encoder')
def test_compress_replaces_the_video_once_and_leaves_efficient_ones(sample_video, tmp_path, capsys):
  from video_agent import compress

  video = tmp_path / 'lecture.mp4'
  video.write_bytes(sample_video.read_bytes())
  before = video.stat().st_size
  (tmp_path / '.lecture.0123abcd.part.mp4').write_bytes(b'half written by a stopped compression')
  other = tmp_path / '.lecture 2.0123abcd.part.mp4'  # another video's
  other.write_bytes(b'x')
  capsys.readouterr()
  assert cli.main(['compress', str(video), '--json']) == 0
  result = json.loads(capsys.readouterr().out)
  assert result['skipped'] is None and result['after'] == video.stat().st_size < before
  _, info = media.probe(video)
  assert next(s for s in info['streams'] if s['codec_type'] == 'video')['codec_name'] == 'av1'
  assert abs(media.duration(info) - 8) < 1
  assert compress.skip_reason(info) == 'already compressed by Video Agent'
  assert cli.main(['compress', str(video), '--json']) == 0
  assert json.loads(capsys.readouterr().out)['skipped'] == 'already compressed by Video Agent'
  assert [path for path in tmp_path.iterdir() if '.part' in path.name] == [other], 'the leftover is gone'
  assert compress.skip_reason({'streams': [{'codec_type': 'video', 'codec_name': 'hevc'}]}).startswith('already HEVC')
  # The state is kept, so a collection's list knows it without opening the file.
  assert compress.known(video) == (True, 'compressed')
  workspace = tmp_path / 'ws'
  assert cli.main(['collection', 'create', '课', str(video), '-o', str(workspace)]) == 0
  capsys.readouterr()
  assert cli.main(['collection', 'list', '-o', str(workspace)]) == 0
  assert json.loads(capsys.readouterr().out)[0]['videos'][0]['compression'] == 'compressed'


def test_compress_check_tells_the_state_and_forgets_it_when_the_file_changes(sample_video, tmp_path, capsys):
  from video_agent import compress

  video = tmp_path / 'clip.mp4'
  video.write_bytes(sample_video.read_bytes())
  capsys.readouterr()
  assert cli.main(['compress', '--check', '--json', str(video)]) == 0
  assert json.loads(capsys.readouterr().out) == {'video': str(video), 'state': None}
  assert compress.known(video) == (True, None)
  assert cli.main(['show', str(video), '-o', str(tmp_path / 'ws')]) == 0
  assert json.loads(capsys.readouterr().out)['compression'] is None
  compress.remember(video, 'not-smaller')  # as after a try whose copy came out larger
  assert cli.main(['compress', '--check', '--json', str(video)]) == 0
  assert json.loads(capsys.readouterr().out)['state'] == 'not-smaller'
  video.write_bytes(video.read_bytes() + b'\0')  # another file now
  assert compress.known(video) == (False, None)


# Stands in for AutoSlides Extractor: writes three slides, the second the first with a line added, and their
# timeline.json, as the real one does with --write-timeline, and prints JSON lines.
FAKE_EXTRACTOR = r"""
import json, subprocess, sys
from pathlib import Path
args = sys.argv[1:]
video, output = Path(args[args.index('--video') + 1]), Path(args[args.index('--output') + 1])
folder = output / f'slides_{video.stem}'
folder.mkdir(parents=True)
pictures = [
  'color=white:s=320x180,drawbox=x=20:y=20:w=200:h=16:color=black:t=fill',
  'color=white:s=320x180,drawbox=x=20:y=20:w=200:h=16:color=black:t=fill,drawbox=x=20:y=60:w=200:h=16:color=black:t=fill',
  'smptebars=s=320x180',
]
events, resolutions = [], {}
for number, (graph, second) in enumerate(zip(pictures, (0.0, 2.0, 5.0)), 1):
  name = f'slide_{number:03d}.jpg'
  subprocess.run(['ffmpeg', '-v', 'error', '-filter_complex', graph + '[v]', '-map', '[v]', '-frames:v', '1', str(folder / name)], check=True)
  events.append({'id': f'e{number}', 'changeAt': second, 'confirmedAt': second + 2, 'initialFile': name})
  resolutions[f'e{number}'] = {'file': name, 'state': 'canonical'}
(folder / 'timeline.json').write_text(json.dumps({'events': events, 'resolutions': resolutions}), encoding='utf-8')
print(json.dumps({'event': 'done', 'slideCount': 3}), flush=True)
"""


def test_autoslides_extractor_finds_the_screen_pages_where_installed(sample_video, tmp_path, monkeypatch):
  script = tmp_path / 'fake_extractor.py'
  script.write_text(FAKE_EXTRACTOR, encoding='utf-8')
  program = tmp_path / 'AutoSlidesExtractor.cmd'
  program.write_text(f'@"{sys.executable}" "{script}" %*\n', encoding='utf-8')
  monkeypatch.setenv('AUTOSLIDES_EXTRACTOR', str(program))
  monkeypatch.setenv('PATH', f'{Path(media.tool("ffmpeg")).parent}{os.pathsep}{os.environ["PATH"]}')
  workspace = tmp_path / 'work'
  assert cli.main(['process', str(sample_video), '-o', str(workspace), '--json']) == 0
  manifest = json.loads((asset_folder(workspace, sample_video.resolve()) / 'manifest.json').read_text(encoding='utf-8'))
  slides = manifest['slide_extraction']['slides']
  assert manifest['slide_extraction']['enabled'] and manifest['screen_pages'] == [], 'its slides stand for the pages'
  # The step with a line added joins the first slide, keeping its time and the fuller picture.
  assert [(item['time_s'], Path(item['path']).name) for item in slides] == [
    (0.0, 'slide_002.jpg'),
    (5.0, 'slide_003.jpg'),
  ]
  assert cli.main(['process', str(sample_video), '-o', str(workspace), '--json', '--force', '--no-extract-slides']) == 0
  manifest = json.loads((asset_folder(workspace, sample_video.resolve()) / 'manifest.json').read_text(encoding='utf-8'))
  assert not manifest['slide_extraction']['enabled'] and manifest['screen_pages'], 'turned off: our own page search'
