"""The cleaned transcript: the original with recurring mishearings corrected (user decision, 2026-10-28).

`transcript.srt` and `transcript.txt` stay as they were acquired. `corrections.json` in the video's folder lists
wrong -> right pairs, and `transcript.clean.srt` / `.txt` are always rebuilt from the original and those pairs, so a
pair can be taken back and nothing is ever lost. Wherever a cleaned transcript exists it is the one used: the
summary context, the window's transcript view, every summary route. Only words are replaced; sentences are not
rewritten, so the cleaned transcript is still what was said.
"""

import json
import re
from pathlib import Path

from . import files, transcript

CORRECTIONS = 'corrections.json'
ORIGINAL = 'transcript'
CLEAN = 'transcript.clean'
WORD = re.compile(r'[A-Za-z0-9_.+-]+')


def load(asset):
  """The video's wrong -> right pairs, in the order they were given."""
  path = Path(asset) / CORRECTIONS
  if not path.is_file():
    return []
  return [tuple(pair) for pair in json.loads(path.read_text(encoding='utf-8')).get('replace', [])]


def save(asset, pairs):
  path = Path(asset) / CORRECTIONS
  if pairs:
    files.write_text(path, json.dumps({'replace': [list(pair) for pair in pairs]}, ensure_ascii=False, indent=2) + '\n')
  else:
    path.unlink(missing_ok=True)


def _pattern(wrong):
  """A Latin word is matched as a whole word, so `react` does not touch `reaction`; Chinese is matched as written,
  which is why only forms that are wrong everywhere belong in the list."""
  escaped = re.escape(wrong)
  return re.compile(rf'(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])' if WORD.fullmatch(wrong) else escaped)


def apply(rows, pairs):
  """Rows with the pairs applied, longest wrong form first (so a longer phrase wins over a word inside it), and the
  changed rows as (start, before, after)."""
  ordered = sorted(pairs, key=lambda pair: len(pair[0]), reverse=True)
  patterns = [(_pattern(wrong), right) for wrong, right in ordered if wrong]
  cleaned, changes = [], []
  for start, end, text in rows:
    new = text
    for pattern, right in patterns:
      new = pattern.sub(lambda _, right=right: right, new)  # the right form as written, no escapes
    cleaned.append((start, end, new))
    if new != text:
      changes.append((start, text, new))
  return cleaned, changes


def original_rows(asset):
  path = Path(asset) / f'{ORIGINAL}.srt'
  return transcript.parse(path.read_text(encoding='utf-8-sig', errors='replace')) if path.is_file() else None


def rebuild(asset, shared=()):
  """Writes the cleaned transcript from the original, the `shared` pairs (a collection's terms) and the video's own,
  or removes it when there are no pairs. Returns the changes."""
  asset = Path(asset)
  rows = original_rows(asset)
  pairs = [*shared, *load(asset)]
  if rows is None or not pairs:
    for suffix in ('.srt', '.txt'):
      (asset / f'{CLEAN}{suffix}').unlink(missing_ok=True)
    return []
  cleaned, changes = apply(rows, pairs)
  transcript.write(cleaned, asset, stem=CLEAN)
  return changes


def rows_in_use(asset):
  """The cleaned rows when there is a cleaned transcript, else the original ones (or None)."""
  path = Path(asset) / f'{CLEAN}.srt'
  if path.is_file():
    return transcript.parse(path.read_text(encoding='utf-8-sig', errors='replace'))
  return original_rows(asset)


def in_use(asset, suffix='.txt'):
  """The transcript file to read: the cleaned one when there is one."""
  for stem in (CLEAN, ORIGINAL):
    path = Path(asset) / f'{stem}{suffix}'
    if path.is_file():
      return path
  return None
