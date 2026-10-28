"""BCut (必剪), Bilibili's free speech recognition, as a transcript source.

The protocol, as public BCut clients use it: ask for an upload slot, PUT the audio in the parts BCut sets (to plain-HTTP
object storage), confirm the upload with the parts' ETags, start a task on the uploaded file, and poll the task until it
holds the utterances. Written for this project (2026-10-28): the parts go up in parallel, every request retries
connection failures and 5xx answers, a throttled request (Bilibili answers 412 or 429) waits minutes rather than
seconds before it is tried again, and the wait for the result follows the audio's length.
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = 'https://member.bilibili.com/x/bcut/rubick-interface'
MODEL = '8'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) video-agent'}
# extract_audio writes AAC at 48 kb/s, so the file's size gives its length, and with it how long to wait.
AUDIO_BYTES_PER_SECOND = 48_000 / 8
UPLOADS_AT_ONCE = 4
# Task states BCut reports; anything else is still waiting or running.
DONE, FAILED = 4, 3
# Bilibili throttles with 412 (or 429) and lifts it after minutes, so these are not left to the quick retries below.
THROTTLED = (412, 429)
PAUSES = (30, 60, 120, 240)


class BcutError(RuntimeError):
  pass


def _session():
  retry = Retry(
    total=5,
    backoff_factor=1,
    status_forcelist=(500, 502, 503, 504),
    allowed_methods=None,  # also POST and PUT: a slot, a part or a task asked for twice does no harm
    raise_on_status=False,  # the last answer comes back, so an error can name its HTTP status
  )
  session = requests.Session()
  session.headers.update(HEADERS)
  for scheme in ('https://', 'http://'):
    session.mount(scheme, HTTPAdapter(max_retries=retry, pool_maxsize=UPLOADS_AT_ONCE))
  return session


class Client:
  def __init__(self, status=print, base=BASE, session=None):
    self.status = status
    self.base = base
    self.http = session or _session()

  def _call(self, method, path, **request):
    pauses = iter(PAUSES)
    while True:
      try:
        reply = self.http.request(method, self.base + path, timeout=60, **request)
      except requests.RequestException as error:
        raise BcutError(f'{path}: {type(error).__name__}') from error
      pause = next(pauses, None) if reply.status_code in THROTTLED else None
      if pause is None:
        break
      self.status(f'BCut: Bilibili is throttling requests (HTTP {reply.status_code}); trying again in {pause} s')
      time.sleep(pause)
    if reply.status_code >= 400:
      raise BcutError(f'{path}: HTTP {reply.status_code}')
    try:
      body = reply.json()
    except ValueError as error:
      raise BcutError(f'{path}: HTTP {reply.status_code}, not JSON') from error
    if body.get('code') != 0:
      raise BcutError(f'{path}: {body.get("message") or body.get("code")}')
    return body.get('data') or {}

  def _put(self, address, part, number, total):
    try:
      reply = self.http.put(address, data=part, timeout=300)
    except requests.RequestException as error:
      raise BcutError(f'audio part {number}/{total}: {type(error).__name__}') from error
    if not reply.ok:
      raise BcutError(f'audio part {number}/{total}: HTTP {reply.status_code}')
    return reply.headers.get('Etag', '').strip('"')

  def upload(self, audio):
    """Uploads the file and returns the address BCut gives it."""
    data = audio.read_bytes()
    slot = self._call(
      'POST',
      '/resource/create',
      json={'type': 2, 'name': audio.name, 'size': len(data), 'ResourceFileType': audio.suffix[1:], 'model_id': MODEL},
    )
    addresses, size = slot['upload_urls'], int(slot['per_size'])
    # The last part takes whatever is left, should the parts BCut asked for not add up to the whole file.
    parts = [data[i * size : (i + 1) * size] for i in range(len(addresses) - 1)] + [data[(len(addresses) - 1) * size :]]
    self.status(f'BCut: uploading {len(data) / 1e6:.1f} MB in {len(parts)} parts')
    with ThreadPoolExecutor(min(UPLOADS_AT_ONCE, len(parts))) as pool:
      tags = list(pool.map(self._put, addresses, parts, range(1, len(parts) + 1), [len(parts)] * len(parts)))
    done = self._call(
      'POST',
      '/resource/create/complete',
      json={
        'InBossKey': slot['in_boss_key'],
        'ResourceId': slot['resource_id'],
        'Etags': ','.join(tags),
        'UploadId': slot['upload_id'],
        'model_id': MODEL,
      },
    )
    return done['download_url']

  def wait(self, task, deadline):
    """Polls the task, slowly at first and then every 10 s, until it holds the utterances."""
    pause, last = 1.0, None
    while True:
      state = self._call('GET', '/task/result', params={'model_id': MODEL, 'task_id': task})
      code = state.get('state')
      if code == DONE:
        return json.loads(state.get('result') or '{}')
      if code == FAILED:
        raise BcutError(f'recognition failed: {state.get("remark") or "BCut gave no reason"}')
      if code != last:
        self.status('BCut: recognising' if code else 'BCut: waiting in the queue')
        last = code
      if time.monotonic() + pause > deadline:
        raise BcutError(f'task {task} not finished in time')
      time.sleep(pause)
      pause = min(pause * 1.5, 10.0)

  def transcribe(self, audio):
    """(start_s, end_s, text) rows for an audio file written by extract_audio."""
    audio = Path(audio)
    length = audio.stat().st_size / AUDIO_BYTES_PER_SECOND
    # BCut usually needs a small fraction of the audio's length; allow its full length plus ten minutes of queue.
    deadline = time.monotonic() + 600 + length
    resource = self.upload(audio)
    task = self._call('POST', '/task', json={'resource': resource, 'model_id': MODEL})['task_id']
    result = self.wait(task, deadline)
    rows = [
      (item['start_time'] / 1000, item['end_time'] / 1000, item['transcript'].strip())
      for item in result.get('utterances') or []
      if item.get('transcript', '').strip()
    ]
    self.status(f'BCut: {len(rows)} lines')
    return rows


def transcribe(audio, status=print):
  return Client(status).transcribe(audio)
