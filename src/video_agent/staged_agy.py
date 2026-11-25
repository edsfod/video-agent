"""The agy command line (Antigravity) as the channel of the staged summary (docs/design/staged.md): one turn is one
`agy -p` with a custom agent that has only view_file, in a new conversation or one it goes on with. The prompt goes in
on stdin, so its length is not limited by the command line."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from . import files

NAME = 'agy'
MODEL = 'gemini-3.8-flash-high'
FIX_MODEL = (
  'gemini-3.8-flash-medium'  # fix turns only handle what the checks list; medium does them as well (2026-11-25)
)
MAX_REFUSED = 3  # refused tool calls in one turn after which the turn is stopped
LIMIT_S = 1800
FIELDS = ('input_tokens', 'cache_read_tokens', 'output_tokens', 'thinking_tokens')

AGENT = """---
name: reader
description: 读给出的文件和图片，按指令用中文写文字。
tools:
  - view_file
mainAgent: true
subagent: false
---
# 系统提示
你按用户的指令读材料和图片，然后用中文回答。只用 view_file 打开文件；互不依赖的文件在同一步里一起打开。回答就是最终结果，不写文件，不运行命令。
"""

REFUSAL = '这一步只能用 view_file 打开消息里列出的文件；不运行命令，不读别的文件。直接按消息的要求写回答。'


class ChannelError(RuntimeError):
  pass


def gate(root, stream=sys.stdin):
  """The PreToolUse hook (`video-agent _staged-gate <root>`): reads inside `root` are allowed, every other call is
  refused with its reason. The custom agent declares only view_file, but agy still runs a tool the model calls without
  it being declared, and a read outside the workspace waits for a permission headless mode cannot give, which ends the
  turn with no reply; with the reason the model goes on and answers."""
  call = json.load(stream)
  tool, args = call.get('toolCall', {}).get('name', ''), call.get('toolCall', {}).get('args', {})
  root = os.path.normcase(os.path.abspath(root))
  path = os.path.normcase(os.path.abspath(str(args.get('Path') or args.get('AbsolutePath') or '')))
  if tool in ('read_file', 'view_file') and (path == root or path.startswith(root + os.sep)):
    return {'decision': 'allow'}
  return {'decision': 'deny', 'reason': REFUSAL}


def _gate_command(root):
  # A frozen build has no `python -m`, so the hook runs through the executable itself (as download.executable does).
  program = [sys.executable] if getattr(sys, 'frozen', False) else [sys.executable, '-m', 'video_agent']
  return ' '.join(f'"{part}"' for part in [*program, '_staged-gate', str(root)])


def prepare(workspace):
  """The custom agent and the hook in `workspace/.agents/`, where agy run in `workspace` finds them."""
  workspace = Path(workspace)
  hooks = {
    'reader-gate': {
      'PreToolUse': [
        {'matcher': '*', 'hooks': [{'type': 'command', 'command': _gate_command(workspace), 'timeout': 10}]}
      ]
    }
  }
  for path, text in (
    (workspace / '.agents' / 'agents' / 'reader.md', AGENT),
    (workspace / '.agents' / 'hooks.json', json.dumps(hooks, ensure_ascii=False, indent=1) + '\n'),
  ):
    if not path.is_file() or path.read_text(encoding='utf-8') != text:
      path.parent.mkdir(parents=True, exist_ok=True)
      files.write_text(path, text)


def turn(prompt, workspace, log, *, conversation=None, model=MODEL, limit_s=LIMIT_S):
  """One turn: {'conversation', 'response', 'calls', 'failed', 'tools', 'tool_names', 'denied', 'usage': {input,
  cache_read, output, thinking}, 'seconds'}. A start that fails (the backend gives an empty conversation id, or agy
  exits before it reads the prompt) is tried again, up to three times. Raises ChannelError when the turn does not
  finish."""
  for attempt in range(3):
    try:
      return _turn(prompt, workspace, log, conversation, model, limit_s)
    except ChannelError as error:
      if not any(sign in str(error) for sign in ('empty conversation id', 'exited before')) or attempt == 2:
        raise
      time.sleep(15)
  raise AssertionError('unreachable')


def _turn(prompt, workspace, log, conversation, model, limit_s):
  command = ['agy', '--model', model, '--agent', 'reader', '--input-format', 'stream-json']
  command += ['--output-format', 'stream-json', '--print-timeout', f'{limit_s}s']
  if conversation:
    command += ['--conversation', conversation]
  message = json.dumps({'event': 'user', 'message': {'content': prompt}}, ensure_ascii=False) + '\n'
  began = time.time()
  try:
    process = subprocess.Popen(
      command,
      stdin=subprocess.PIPE,
      stdout=subprocess.PIPE,
      stderr=subprocess.PIPE,
      cwd=workspace,
      text=True,
      encoding='utf-8',
      errors='replace',
      creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
    )
  except FileNotFoundError as error:
    raise ChannelError(
      '找不到 agy（Antigravity 命令行）；用 winget install Google.AntigravityCLI 安装，它用 Antigravity 桌面版的登录'
    ) from error
  try:
    process.stdin.write(message)
    process.stdin.close()
  except OSError as error:
    process.kill()
    raise ChannelError(f'agy exited before it read the prompt ({error}): {process.stderr.read()[-500:]}') from error
  # read the events as they come, so a turn that keeps calling refused tools can be stopped early
  lines, refused, wandered = [], 0, False
  for line in process.stdout:
    lines.append(line)
    if '"state":"ERROR"' in line and '"step_type":"tool"' in line:
      refused += 1
      if refused >= MAX_REFUSED:
        wandered = True
        process.kill()
        break
  process.wait()
  stderr = process.stderr.read()
  stdout = ''.join(lines)
  Path(log).parent.mkdir(parents=True, exist_ok=True)
  with open(log, 'a', encoding='utf-8', newline='\n') as out:
    out.write(f'===== {time.strftime("%H:%M:%S")} {" ".join(command)}\n{stdout}')
    if stderr.strip():
      out.write('--- stderr\n' + stderr[-2000:] + '\n')
  if wandered:
    raise ChannelError(f'被拒绝的工具调用达到 {MAX_REFUSED} 次，已停止这一轮')
  return parse(stdout, stderr, conversation, began)


def parse(stdout, stderr='', conversation=None, began=None):
  """The turn's result from agy's events. A resumed conversation's result.usage counts the whole conversation, so the
  usage is the sum of this turn's calls; a call that ends in ERROR (agy calls again by itself) has still read and
  thought, so it counts, and is counted apart."""
  result, calls, failed, tools, found_id, names = None, 0, 0, 0, conversation, {}
  used = dict.fromkeys(FIELDS, 0)
  for line in stdout.splitlines():
    try:
      event = json.loads(line)
    except ValueError:
      continue
    found_id = found_id or event.get('conversation_id')
    if event.get('event') == 'step_update':
      step = event['step_update']
      if step.get('state') not in ('DONE', 'ERROR'):
        continue
      if step.get('step_type') == 'agent_response' and step.get('usage'):
        calls += step.get('state') == 'DONE'
        failed += step.get('state') == 'ERROR'
        for field in FIELDS:
          used[field] += int(step['usage'].get(field) or 0)
      elif step.get('step_type') == 'tool' and step.get('state') == 'DONE':
        tools += 1
        names[step.get('tool_name')] = names.get(step.get('tool_name'), 0) + 1
    elif event.get('event') == 'result':
      result = event['result']
  if not result or result.get('status') != 'SUCCESS':
    raise ChannelError(f'没有完成：{(result or {}).get("error") or stderr.strip()[-300:]}')
  return {
    'conversation': result.get('conversation_id') or found_id,
    'response': result.get('response') or '',
    'calls': calls,
    'failed': failed,
    'tools': tools,
    'tool_names': names,
    'denied': [d.get('action') for d in result.get('denied_actions') or []],
    'usage': {
      'input': used['input_tokens'],
      'cache_read': used['cache_read_tokens'],
      'output': used['output_tokens'],
      'thinking': used['thinking_tokens'],
    },
    'seconds': round(time.time() - began, 1) if began else 0,
  }
