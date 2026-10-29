"""The model APIs a summary can be written with: Anthropic's Messages API and any OpenAI-compatible Chat Completions
API (a local Ollama, ModelScope and the like). Each is a Provider: where its model list is, whether it needs a key, and
one exchange with the model, including rounds of the frame tool. Adding a provider is a class here and its defaults in
settings.PROVIDERS.
"""

import base64
import json
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry


class SummaryError(RuntimeError):
  pass


FRAME_TOOL = {
  'name': 'frame',
  'description': (
    'Save the video frame at a given time and look at it. Use it where the speaker points at the screen or the '
    'transcript is unclear and no frame you have is near. Returns the image and its relative path for linking.'
  ),
  'schema': {
    'type': 'object',
    'properties': {'time': {'type': 'string', 'description': 'Time in the video as HH:MM:SS, MM:SS or seconds'}},
    'required': ['time'],
  },
}

# How hard the model thinks, chosen per summary (user request, 2026-10-29). OpenAI-compatible APIs take it as
# `reasoning_effort`; Anthropic's as an extended-thinking budget, in tokens, added to the output allowance (Claude
# judgment: the budgets). Not sent when not chosen, so a model or server without it is not refused.
EFFORTS = ('low', 'medium', 'high')
THINKING_BUDGET = {'low': 2000, 'medium': 8000, 'high': 24000}


def _session():
  http = requests.Session()
  retry = Retry(
    4, backoff_factor=3, status_forcelist=[429, 500, 502, 503, 504, 529], allowed_methods=None, raise_on_status=False
  )
  for scheme in ('https://', 'http://'):
    http.mount(scheme, HTTPAdapter(max_retries=retry))
  return http


def _post(http, url, headers, body):
  try:
    reply = http.post(url, headers=headers, json=body, timeout=600)
  except requests.RequestException as error:
    raise SummaryError(f'{url}: request failed ({type(error).__name__})') from error
  if reply.status_code >= 400:
    raise SummaryError(f'{url}: HTTP {reply.status_code}: {reply.text[:500]}')
  try:
    return reply.json()
  except ValueError as error:
    raise SummaryError(f'{url}: response was not valid JSON') from error


def _encode(path):
  return base64.b64encode(Path(path).read_bytes()).decode('ascii')


class Provider:
  """One kind of model API. `ask` sends the system prompt, the intro text and the labelled images, runs the frame tool
  (`tools.frame(arguments)` gives a saved image or None, and a note) as often as the model asks, and returns its text."""

  name = ''
  needs_key = False

  def models_request(self, config, key):
    """The URL and headers of the provider's model list."""
    raise NotImplementedError

  def ask(self, http, config, key, system, intro, images, tools):
    raise NotImplementedError


class Anthropic(Provider):
  name = 'anthropic'
  needs_key = True

  def models_request(self, config, key):
    return f'{config["base_url"]}/v1/models?limit=1000', {'x-api-key': key or '', 'anthropic-version': '2023-06-01'}

  def ask(self, http, config, key, system, intro, images, tools):
    url = f'{config["base_url"]}/v1/messages'
    headers = {'x-api-key': key, 'anthropic-version': '2023-06-01'}
    content = [{'type': 'text', 'text': intro}]
    for label, path in images:
      content += [
        {'type': 'text', 'text': label},
        {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': _encode(path)}},
      ]
    messages = [{'role': 'user', 'content': content}]
    body = {'model': config['model'], 'max_tokens': 16000, 'system': system, 'messages': messages}
    if config.get('effort'):
      budget = THINKING_BUDGET[config['effort']]
      body |= {'max_tokens': 16000 + budget, 'thinking': {'type': 'enabled', 'budget_tokens': budget}}
    if tools:
      body['tools'] = [
        {'name': FRAME_TOOL['name'], 'description': FRAME_TOOL['description'], 'input_schema': FRAME_TOOL['schema']}
      ]
    while True:
      answer = _post(http, url, headers, body)
      blocks = answer.get('content') or []
      calls = [block for block in blocks if block.get('type') == 'tool_use']
      if answer.get('stop_reason') != 'tool_use' or not calls:
        return ''.join(block.get('text', '') for block in blocks if block.get('type') == 'text')
      messages.append({'role': 'assistant', 'content': blocks})
      results = []
      for call in calls:
        path, note = tools.frame(call.get('input'))
        result = [{'type': 'text', 'text': note}]
        if path:
          result.append(
            {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': _encode(path)}}
          )
        results.append({'type': 'tool_result', 'tool_use_id': call['id'], 'content': result, 'is_error': path is None})
      messages.append({'role': 'user', 'content': results})


class OpenAICompatible(Provider):
  name = 'openai'

  def models_request(self, config, key):
    return f'{config["base_url"]}/models', {'Authorization': f'Bearer {key}'} if key else {}

  def ask(self, http, config, key, system, intro, images, tools):
    url = f'{config["base_url"]}/chat/completions'
    headers = {'Authorization': f'Bearer {key}'} if key else {}
    content = [{'type': 'text', 'text': intro}]
    for label, path in images:
      content += [
        {'type': 'text', 'text': label},
        {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{_encode(path)}'}},
      ]
    messages = [{'role': 'system', 'content': system}, {'role': 'user', 'content': content}]
    body = {'model': config['model'], 'messages': messages}
    if config.get('effort'):
      body['reasoning_effort'] = config['effort']
    if tools:
      body['tools'] = [
        {
          'type': 'function',
          'function': {
            'name': FRAME_TOOL['name'],
            'description': FRAME_TOOL['description'],
            'parameters': FRAME_TOOL['schema'],
          },
        }
      ]
    while True:
      answer = _post(http, url, headers, body)
      try:
        message = answer['choices'][0]['message']
      except (KeyError, IndexError, TypeError) as error:
        raise SummaryError(f'{url}: unexpected response shape') from error
      calls = message.get('tool_calls') or []
      if not calls:
        return message.get('content') or ''
      messages.append({'role': 'assistant', 'content': message.get('content'), 'tool_calls': calls})
      # Tool messages carry text only here, so the images follow in one user message.
      shown = []
      for call in calls:
        try:
          arguments = json.loads(call['function'].get('arguments') or '{}')
        except json.JSONDecodeError:
          arguments = {}
        path, note = tools.frame(arguments)
        messages.append({'role': 'tool', 'tool_call_id': call['id'], 'content': note})
        if path:
          shown += [
            {'type': 'text', 'text': note},
            {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{_encode(path)}'}},
          ]
      if shown:
        messages.append({'role': 'user', 'content': shown})


PROVIDERS = {provider.name: provider for provider in (Anthropic(), OpenAICompatible())}


def provider(config, key):
  """The provider `config` names, once it is known to have the key it needs."""
  found = PROVIDERS[config['provider']]
  if found.needs_key and not key:
    raise SummaryError(f'No API key for {found.name}; run: video-agent config --provider {found.name} --set-key')
  return found


def ask(config, key, system, intro, images, tools):
  """The model's text for one summary or collection text, by the provider `config` names."""
  return provider(config, key).ask(_session(), config, key, system, intro, images, tools)


def list_models(config, key):
  """The provider's model IDs from its model list (GET …/models), which costs no tokens."""
  url, headers = PROVIDERS[config['provider']].models_request(config, key)
  try:
    reply = requests.get(url, headers=headers, timeout=30)
  except requests.RequestException as error:
    raise SummaryError(f'{url}: request failed ({type(error).__name__})') from error
  if reply.status_code >= 400:
    raise SummaryError(f'{url}: HTTP {reply.status_code}: {reply.text[:300]}')
  try:
    entries = reply.json().get('data') or reply.json().get('models') or []
  except (ValueError, AttributeError) as error:
    raise SummaryError(f'{url}: the model list was not JSON with a data list') from error
  return sorted({entry.get('id') or entry.get('name') for entry in entries if isinstance(entry, dict)} - {None})
