"""Writes gui/src/cli-types.d.ts, the TypeScript types of what the CLI prints with --json, from
src/video_agent/contract.py. Run it after changing contract.py; a test fails while the file is out of date.

  uv run scripts/cli_types.py
"""

import inspect
import sys
import types
import typing
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src'))

from video_agent import contract

TARGET = ROOT / 'gui' / 'src' / 'cli-types.d.ts'
ALIASES = {'CompressionState': contract.CompressionState}


def _type(shape, top=False):
  if not top:
    for name, alias in ALIASES.items():
      if shape == alias:
        return name
  if shape is typing.Any:
    return 'unknown'
  if shape is None or shape is type(None):
    return 'null'
  if shape in (int, float):
    return 'number'
  if shape is str:
    return 'string'
  if shape is bool:
    return 'boolean'
  if typing.is_typeddict(shape):
    return shape.__name__
  origin, arguments = typing.get_origin(shape), typing.get_args(shape)
  if origin in (typing.Union, types.UnionType):
    return ' | '.join(_type(option) for option in arguments)
  if origin is typing.Literal:
    return ' | '.join(f"'{value}'" for value in arguments)
  if origin is list:
    item = _type(arguments[0])
    return f'({item})[]' if ' | ' in item else f'{item}[]'
  if origin is dict:
    return f'Record<string, {_type(arguments[1])}>'
  raise TypeError(f'no TypeScript type for {shape!r}')


def _comment(text, indent=''):
  lines = inspect.cleandoc(text).splitlines()
  return (
    [f'{indent}/** {lines[0]}']
    + [f'{indent} * {line}' if line else f'{indent} *' for line in lines[1:]]
    + [f'{indent} */']
    if len(lines) > 1
    else [f'{indent}/** {lines[0]} */']
  )


def render():
  out = [
    '// The JSON the video-agent CLI prints with --json, and its manifest.json and collection.json.',
    '// Written by scripts/cli_types.py from src/video_agent/contract.py; change that file, not this one.',
    '',
    f'export type JsonVersion = {contract.JSON_VERSION};',
    f'export type CollectionVersion = {contract.COLLECTION_VERSION};',
  ]
  for name, alias in ALIASES.items():
    out += ['', f'export type {name} = {_type(alias, top=True)};']
  for value in vars(contract).values():
    if not (typing.is_typeddict(value) and value.__module__ == contract.__name__):
      continue
    out.append('')
    if value.__doc__:
      out += _comment(value.__doc__)
    out.append(f'export interface {value.__name__} {{')
    for field, shape in typing.get_type_hints(value).items():
      optional = '?' if field in value.__optional_keys__ else ''
      out.append(f'  {field}{optional}: {_type(shape)};')
    out.append('}')
  out += ['', '/** What each command prints; a command that prints several lines gives the type of one line. */']
  out.append('export interface CliOutputs {')
  out += [f'  {command}: {_type(shape)};' for command, shape in contract.OUTPUTS.items()]
  out.append('}')
  return '\n'.join(out) + '\n'


if __name__ == '__main__':
  TARGET.write_text(render(), encoding='utf-8', newline='\n')
  print(TARGET)
