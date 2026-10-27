"""Shared fixtures: a short synthetic video with a sidecar subtitle file, and a scripted fake model server."""

import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from video_agent.media import tool

SUBTITLES = """1
00:00:00,500 --> 00:00:02,500
大家好，今天讲测试视频

2
00:00:03,000 --> 00:00:05,000
我们看看这张图表
"""


@pytest.fixture(autouse=True)
def own_appdata(tmp_path_factory, monkeypatch):
  """Settings and the user's copy of the summary rules come from %APPDATA%; never read the real ones."""
  monkeypatch.setenv('APPDATA', str(tmp_path_factory.mktemp('appdata')))


@pytest.fixture(scope='session')
def sample_video(tmp_path_factory):
  """An 8-second H.264 video with a sine tone, its colours changing at 4 s, and a matching `.srt` beside it."""
  folder = tmp_path_factory.mktemp('media')
  video = folder / 'sample clip [test].mp4'
  subprocess.run(
    [
      tool('ffmpeg'),
      '-y',
      '-hide_banner',
      '-loglevel',
      'error',
      '-f',
      'lavfi',
      '-i',
      'testsrc=duration=4:size=320x240:rate=10',
      '-f',
      'lavfi',
      '-i',
      'smptebars=duration=4:size=320x240:rate=10',
      '-f',
      'lavfi',
      '-i',
      'sine=frequency=440:duration=8',
      '-filter_complex',
      '[0:v][1:v]concat=n=2:v=1:a=0[v]',
      '-map',
      '[v]',
      '-map',
      '2:a',
      '-c:v',
      'libx264',
      '-pix_fmt',
      'yuv420p',
      '-c:a',
      'aac',
      '-shortest',
      str(video),
    ],
    check=True,
  )
  video.with_suffix('.srt').write_text(SUBTITLES, encoding='utf-8')
  return video


class FakeModel:
  """Serves the scripted JSON replies in order and records each request body."""

  def __init__(self, replies):
    self.replies, self.requests = list(replies), []
    model = self

    class Handler(BaseHTTPRequestHandler):
      def do_POST(self):
        body = self.rfile.read(int(self.headers['Content-Length']))
        model.requests.append({'path': self.path, 'headers': dict(self.headers), 'body': json.loads(body)})
        reply = json.dumps(model.replies.pop(0)).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)

      def log_message(self, *args):
        pass

    self.server = HTTPServer(('127.0.0.1', 0), Handler)
    self.url = f'http://127.0.0.1:{self.server.server_port}'
    threading.Thread(target=self.server.serve_forever, daemon=True).start()

  def close(self):
    self.server.shutdown()


@pytest.fixture
def fake_model():
  servers = []

  def start(replies):
    servers.append(FakeModel(replies))
    return servers[-1]

  yield start
  for server in servers:
    server.close()


@pytest.fixture
def no_proxy(monkeypatch):
  """Keep requests to the fake server off any system proxy."""
  monkeypatch.setenv('NO_PROXY', '127.0.0.1,localhost')
  monkeypatch.setenv('no_proxy', '127.0.0.1,localhost')


def read(path):
  return Path(path).read_text(encoding='utf-8')
