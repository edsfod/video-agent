"""BCut upload/transcription adapter, adapted from edsfod/yanhe-agent by the same author."""

import json
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

BASE = 'https://member.bilibili.com/x/bcut/rubick-interface'
MODEL_ID = 7
THROTTLED = (412, 429)
PAUSES = (30, 60, 120, 240)
DONE, FAILED = 4, 3


class BcutError(RuntimeError):
  pass


class BCut:
  def __init__(self, status=print):
    self.status = status
    self.http = requests.Session()
    self.http.headers['User-Agent'] = 'Mozilla/5.0'
    # raise_on_status=False hands back the last response, so errors keep their HTTP status.
    retry = Retry(
      3, backoff_factor=2, status_forcelist=[500, 502, 503, 504], allowed_methods=None, raise_on_status=False
    )
    # BCut returns plain-HTTP upload URLs (BOSS object storage), so both schemes need the retry policy.
    for scheme in ('https://', 'http://'):
      self.http.mount(scheme, HTTPAdapter(max_retries=retry))

  def ask(self, method, path, **request):
    pauses = iter(PAUSES)
    while True:
      try:
        reply = self.http.request(method, BASE + path, timeout=60, **request)
      except requests.RequestException as error:
        raise BcutError(f'{path}: network request failed ({type(error).__name__})') from error
      pause = next(pauses, None) if reply.status_code in THROTTLED else None
      if pause is None:
        break
      self.status(f'BCut {path} returned HTTP {reply.status_code}; retrying in {pause}s')
      time.sleep(pause)
    if reply.status_code >= 400:
      raise BcutError(f'{path}: HTTP {reply.status_code}')
    try:
      answer = reply.json()
    except ValueError as error:
      raise BcutError(f'{path}: response was not valid JSON (HTTP {reply.status_code})') from error
    if answer.get('code') != 0:
      raise BcutError(f'{path}: {answer.get("message") or answer.get("code")}')
    return answer.get('data') or {}

  def upload(self, audio):
    size = audio.stat().st_size
    self.status('BCut: requesting an upload slot')
    slot = self.ask(
      'POST',
      '/resource/create',
      data={'type': 2, 'name': audio.name, 'size': size, 'resource_file_type': 'm4a', 'model_id': MODEL_ID},
    )
    tags = []
    with audio.open('rb') as sound:
      for number, address in enumerate(slot['upload_urls'], 1):
        self.status(f'BCut: uploading audio chunk {number}/{len(slot["upload_urls"])}')
        try:
          stored = self.http.put(address, data=sound.read(slot['per_size']), timeout=120)
        except requests.RequestException as error:
          raise BcutError(f'audio chunk {number}: upload request failed ({type(error).__name__})') from error
        if stored.status_code >= 400:
          raise BcutError(f'audio chunk {number}: upload returned HTTP {stored.status_code}')
        tags.append(stored.headers['Etag'])
    self.status('BCut: finalizing audio upload')
    finished = {
      'in_boss_key': slot['in_boss_key'],
      'resource_id': slot['resource_id'],
      'etags': ','.join(tags),
      'upload_id': slot['upload_id'],
      'model_id': MODEL_ID,
    }
    return self.ask('POST', '/resource/create/complete', data=finished)['download_url']

  def submit(self, resource):
    self.status('BCut: submitting recognition task')
    return self.ask('POST', '/task', json={'resource': resource, 'model_id': str(MODEL_ID)})['task_id']

  def result(self, task):
    state = self.ask('GET', '/task/result', params={'model_id': MODEL_ID, 'task_id': task})
    if state.get('state') == FAILED:
      raise BcutError(f'/task/result: recognition failed: {state.get("remark") or "no reason given"}')
    if state.get('state') != DONE:
      return None
    return [
      (utterance['start_time'] / 1000, utterance['end_time'] / 1000, utterance['transcript'])
      for utterance in json.loads(state['result']).get('utterances', [])
    ]

  def transcribe(self, audio, timeout=7200):
    self.status(f'Uploading {audio.stat().st_size / 1e6:.1f} MB of audio to Bilibili BCut')
    task = self.submit(self.upload(audio))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
      self.status('BCut: waiting for transcription result')
      rows = self.result(task)
      if rows is not None:
        return rows
      time.sleep(10)
    raise TimeoutError(f'BCut task {task} did not finish within {timeout // 60} minutes')
