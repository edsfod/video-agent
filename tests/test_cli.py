"""Subtitle parsing, times, process, frame, download with a fake yt-dlp, and summarize settings."""

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from video_agent import cli, download, media, settings, transcript
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
    print(json.dumps({'_type': 'playlist' if 'list' in url else 'video', 'id': 'x'}))
    sys.exit(0)
  if 'fail' in url or ('subtitle-error' in url and '--write-subs' in args):
    sys.exit(1)
  template = args[args.index('--output') + 1]
  path = Path(template.replace('%(title)s', 'Clip').replace('%(id)s', 'abc').replace('%(ext)s', 'mp4'))
  path.write_bytes(b'video')
  if '--write-subs' in args:
    path.with_suffix('.ai-zh.srt').write_text('1\\n00:00:01,000 --> 00:00:02,000\\nhi\\n', encoding='utf-8')
  print(path)
""")


@pytest.fixture
def fake_yt_dlp(tmp_path, monkeypatch):
  script = tmp_path / 'fake_yt_dlp.py'
  script.write_text(FAKE_YT_DLP, encoding='utf-8')
  monkeypatch.setattr(download, 'executable', lambda explicit=None: [sys.executable, str(script)])


def test_download_returns_paths_and_refuses_playlists(fake_yt_dlp, tmp_path):
  messages = []
  paths, failed = download.download_urls(
    ['https://example.com/video', 'https://example.com/list', 'https://example.com/fail'],
    tmp_path / 'downloads',
    status=messages.append,
  )
  assert [path.name for path in paths] == ['Clip [abc].mp4']
  assert failed == 2
  assert any('pass --playlist' in message for message in messages)

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
  command = [media.tool('ffmpeg'), '-y', '-v', 'error', '-f', 'lavfi', '-i', 'color=gray:size=160x120:rate=5:d=3']
  subprocess.run([*command, '-pix_fmt', 'yuv420p', str(still)], check=True)
  if bundled:
    monkeypatch.setattr(media.shutil, 'which', lambda name: None)
  assert media.scene_frames(still, tmp_path / 'scenes', 0.35) == []


def test_versions_match():
  from video_agent import __version__

  root = Path(__file__).resolve().parents[1]
  for name in ('plugin.json', '.claude-plugin/plugin.json', 'gui/package.json'):
    assert json.loads((root / name).read_text(encoding='utf-8'))['version'] == __version__, name
  wheel = f'releases/download/v{__version__}/video_agent-{__version__}-py3-none-any.whl'
  assert (root / 'skills/video-agent/SKILL.md').read_text(encoding='utf-8').count(wheel) == 2
  assert wheel in (root / 'README.md').read_text(encoding='utf-8')


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
