"""The BCut client against a local server that speaks its protocol: a slot, parts PUT in parallel, the confirmation
with their ETags, a task polled through its states, and the utterances as rows."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from video_agent.providers import bcut


class FakeBcut:
  def __init__(self, states=(0, 1, 4), parts=3, utterances=None):
    self.states = list(states)
    self.parts = parts
    self.utterances = (
      utterances
      if utterances is not None
      else [
        {'start_time': 500, 'end_time': 2500, 'transcript': '第一句'},
        {'start_time': 3000, 'end_time': 4000, 'transcript': '  '},
        {'start_time': 4200, 'end_time': 6000, 'transcript': '第二句 '},
      ]
    )
    self.received = {}
    self.puts_at_once = 0
    self.completed = None
    self.lock = threading.Lock()
    self.running = 0
    fake = self

    class Handler(BaseHTTPRequestHandler):
      def log_message(self, *args):
        pass

      def reply(self, data, code=0):
        body = json.dumps({'code': code, 'message': 'busy' if code else '', 'data': data}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

      def body(self):
        return self.rfile.read(int(self.headers.get('Content-Length') or 0))

      def do_POST(self):
        path = urlparse(self.path).path
        data = json.loads(self.body() or b'{}')
        if path.endswith('/resource/create'):
          size = -(-data['size'] // fake.parts)
          host = f'http://127.0.0.1:{fake.server.server_port}'
          urls = [f'{host}/part/{i}' for i in range(fake.parts)]
          return self.reply(
            {'in_boss_key': 'key', 'resource_id': 'r1', 'upload_id': 'u1', 'upload_urls': urls, 'per_size': size}
          )
        if path.endswith('/resource/create/complete'):
          fake.completed = data
          return self.reply({'download_url': 'https://boss.example/audio'})
        if path.endswith('/task'):
          return self.reply({'task_id': 't1'})
        self.send_response(404)
        self.end_headers()

      def do_PUT(self):
        with fake.lock:
          fake.running += 1
          fake.puts_at_once = max(fake.puts_at_once, fake.running)
        threading.Event().wait(0.2)  # long enough for the other parts to start
        number = int(self.path.rsplit('/', 1)[1])
        fake.received[number] = self.body()
        with fake.lock:
          fake.running -= 1
        self.send_response(200)
        self.send_header('ETag', f'"tag{number}"')
        self.send_header('Content-Length', '0')
        self.end_headers()

      def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        assert query['task_id'] == ['t1']
        state = fake.states.pop(0) if len(fake.states) > 1 else fake.states[0]
        result = json.dumps({'utterances': fake.utterances}) if state == 4 else ''
        return self.reply({'state': state, 'result': result, 'remark': 'no speech' if state == 3 else ''})

    self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=self.server.serve_forever, daemon=True).start()
    self.base = f'http://127.0.0.1:{self.server.server_port}/x/bcut/rubick-interface'

  def close(self):
    self.server.shutdown()


@pytest.fixture
def audio(tmp_path):
  path = tmp_path / 'audio.m4a'
  path.write_bytes(bytes(range(256)) * 40 + b'tail')  # 10244 bytes: three parts, the last one shorter
  return path


@pytest.fixture
def quick(monkeypatch):
  monkeypatch.setattr(bcut.time, 'sleep', lambda seconds: None)


def test_parts_go_up_in_parallel_and_the_utterances_come_back_as_rows(audio, quick):
  fake = FakeBcut()
  messages = []
  try:
    rows = bcut.Client(messages.append, base=fake.base).transcribe(audio)
  finally:
    fake.close()
  assert rows == [(0.5, 2.5, '第一句'), (4.2, 6.0, '第二句')]
  assert b''.join(fake.received[i] for i in range(3)) == audio.read_bytes()
  assert fake.puts_at_once > 1
  assert fake.completed['Etags'] == 'tag0,tag1,tag2' and fake.completed['InBossKey'] == 'key'
  assert messages == [
    'BCut: uploading 0.0 MB in 3 parts',
    'BCut: waiting in the queue',
    'BCut: recognising',
    'BCut: 2 lines',
  ]


def test_a_failed_task_and_an_error_code_say_why(audio, quick):
  fake = FakeBcut(states=(1, 3))
  try:
    with pytest.raises(bcut.BcutError, match='no speech'):
      bcut.Client(lambda message: None, base=fake.base).transcribe(audio)
  finally:
    fake.close()


def test_a_task_that_never_finishes_stops_at_the_deadline(audio, quick, monkeypatch):
  fake = FakeBcut(states=(1,))
  clock = iter(range(0, 100000, 50))
  monkeypatch.setattr(bcut.time, 'monotonic', lambda: next(clock))
  try:
    with pytest.raises(bcut.BcutError, match='not finished in time'):
      bcut.Client(lambda message: None, base=fake.base).transcribe(audio)
  finally:
    fake.close()


def test_throttling_waits_minutes_and_then_goes_on(audio, monkeypatch):
  """Bilibili's 412 is waited out with long pauses, said in the progress, not retried at once or reported as a failure."""
  fake = FakeBcut()
  slept, messages = [], []
  monkeypatch.setattr(bcut.time, 'sleep', slept.append)
  answers = iter([412, 412])
  real = bcut.requests.Session.request

  def throttled(session, method, url, **request):
    if url.endswith('/resource/create'):
      code = next(answers, None)
      if code:
        reply = bcut.requests.Response()
        reply.status_code = code
        return reply
    return real(session, method, url, **request)

  monkeypatch.setattr(bcut.requests.Session, 'request', throttled)
  try:
    rows = bcut.Client(messages.append, base=fake.base).transcribe(audio)
  finally:
    fake.close()
  assert len(rows) == 2
  assert slept[:2] == [30, 60]
  assert messages[0] == 'BCut: Bilibili is throttling requests (HTTP 412); trying again in 30 s'
