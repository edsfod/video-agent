"""Subtitle parsing, times, process, frame, download with a fake yt-dlp, and summarize settings."""

import json
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
  if 'fail' in url:
    sys.exit(1)
  template = args[args.index('--output') + 1]
  path = Path(template.replace('%(title)s', 'Clip').replace('%(id)s', 'abc').replace('%(ext)s', 'mp4'))
  path.write_bytes(b'video')
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
