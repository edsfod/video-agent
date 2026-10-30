"""Saving a text written elsewhere (a chat AI's answer to `pack`, an Agent's draft, the user's own) as a video's
summary or a collection's overview or study guide, and repairing what chat AIs do to it on the way: a code fence
around it, links rewritten into searches or a sandbox, frames asked for by time, a 字幕改正 section, a 画面调整
section (picture_review.py) and a 复查 section, with the checks of a chat AI's rounds (summary_review.py).
"""

import re
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import collection, files, media, picture_review, processor, summary_review, templates, versions
from .evidence import SUMMARY_NAME, processed, video_line
from .model_api import SummaryError


def clean(text):
  """The text with Windows line ends made plain and a fence around the whole of it (```markdown) taken off."""
  text = text.replace('\r\n', '\n').replace('\r', '\n').strip()
  fenced = re.fullmatch(r'(`{3,}|~{3,})(?:markdown|md)?[ \t]*\n(.*)\n\1', text, re.DOTALL)
  return (fenced.group(2) if fenced else text).strip() + '\n'


# Chat AIs rewrite links they cannot resolve: Gemini wraps a relative path in a search
# (https://www.google.com/search?q=frames/…), ChatGPT puts it under its sandbox (sandbox:/mnt/data/<zip>/frames/…).
LINK = re.compile(r'(\]\(<?)([^()<>\s]+)(>?\))')
LOCAL_ROOTS = ('frames/', 'transcript', 'summary-context.md', '../')


def _local_target(target, base):
  """The relative path a rewritten link stands for, when that file is in `base`; None for a link to leave alone."""
  candidates = []
  parsed = urlparse(target)
  if parsed.scheme in ('http', 'https'):
    for values in parse_qs(parsed.query).values():
      candidates += values
  if parsed.scheme in ('http', 'https', 'sandbox', 'file') or target.startswith('/'):
    path = unquote(parsed.path if parsed.scheme else target)
    for root in LOCAL_ROOTS:
      if root in path:
        candidates.append(path[path.index(root) :])
  for candidate in candidates:
    candidate = unquote(candidate).strip()
    if candidate.startswith(LOCAL_ROOTS) and (Path(base) / candidate).exists():
      return candidate
  return None


def repair_links(text, base):
  """Puts back the relative links a chat AI turned into search or sandbox links (user report, 2026-10-28)."""
  return LINK.sub(lambda m: m[1] + (_local_target(m[2], base) or m[2]) + m[3], text)


# A chat AI cannot run `video-agent fix`; the prompt asks it to list recurring mishearings in this section instead.
CORRECTIONS_HEADING = '字幕改正'
CORRECTIONS = re.compile(rf'^##\s*{CORRECTIONS_HEADING}\s*\n(.*?)(?=^##\s|\Z)', re.MULTILINE | re.DOTALL)
PAIR = re.compile(r'^\s*(?:[-*]\s*)?`?(.+?)`?\s*(?:→|->|=>)\s*`?(.+?)`?\s*$')


def take_corrections(text):
  """(summary without the 字幕改正 section, [(wrong, right)] it listed)."""
  found = CORRECTIONS.search(text)
  if not found:
    return text, []
  pairs = [(m[1], m[2]) for line in found[1].splitlines() if (m := PAIR.match(line)) and m[1] != m[2]]
  return (text[: found.start()] + text[found.end() :]).rstrip() + '\n', pairs


# A chat AI cannot take a frame itself; it marks the time of a picture the material lacks, and the import takes it.
CAPTURE = '补截'
# Also inside a link a chat AI rewrote, such as Gemini's https://www.google.com/search?q=补截:00:12:34.
CAPTURE_LINK = re.compile(rf'\]\(<?[^()<>\s]*?{CAPTURE}[:：]\s*((?:\d{{1,2}}:)?\d{{1,2}}:\d{{2}})\s*>?\)')


def _capture_frames(text, video, asset, length, status):
  """Takes the frames the summary asks for with CAPTURE links and points the links at them."""

  def take(match):
    second = sum(int(part) * 60**place for place, part in enumerate(reversed(match[1].split(':'))))
    try:
      path = media.save_frame(video, asset, second, length)
    except media.MediaError as error:
      status(f'{CAPTURE} {match[1]}: {error}')
      return f']({CAPTURE}失败:{match[1]})'
    status(f'{CAPTURE} {match[1]}: {path.name}')
    return f']({path.relative_to(asset).as_posix()})'

  return CAPTURE_LINK.sub(take, text)


def import_summary(
  video,
  workspace,
  text,
  *,
  overwrite=False,
  source='',
  note='',
  rounds=False,
  template=None,
  status=lambda message: None,
):
  """Saves a summary written elsewhere, such as by a chat AI from `pack`, as 总结.md: a ```markdown fence is removed,
  rewritten links point at the video's files again, frames asked for with CAPTURE links are taken, the 视频 line is the
  one this program writes, a 字幕改正 section goes into the cleaned transcript and a 画面调整 section into
  picture-review.json, with the candidates it asks for taken. With a summary there already, the
  new one is kept as a version unless `overwrite` makes it current (versions.py). With `rounds` (a chat AI's answer,
  written to `template`), a 复查 section is taken off and the summary checked for the next round. Returns (path
  written, corrections applied)."""
  video, info, asset, manifest = processed(video, workspace)
  text, pairs = take_corrections(clean(text))
  pictures = bool(picture_review.SECTION.search(text))
  text, unused, wanted = picture_review.take(text)
  text, review = summary_review.take(text) if rounds else (text, None)
  if len(text.strip()) < 40:
    raise SummaryError('The summary to import is empty or too short')
  text = repair_links(text, asset)
  length = manifest.get('duration_s') or media.duration(info)
  line = video_line(video, length)
  text = re.sub(r'^视频：.*?时长：[0-9:]+', lambda _: line, text, count=1, flags=re.MULTILINE)
  with files.video_lock(asset, 'import the summary'):
    text = _capture_frames(text, video, asset, length, status)
    target, _ = versions.save(asset / SUMMARY_NAME, text, source=source or '导入', note=note, make_current=overwrite)
    if unused or wanted or (asset / picture_review.NAME).is_file():
      picture_review.apply(video, asset, target, unused, wanted, length, status)
      if unused:
        processor.write_context(asset)
    if pairs:
      from . import corrections

      known = [pair for pair in corrections.load(asset) if pair[0] not in {wrong for wrong, _ in pairs}]
      corrections.save(asset, known + pairs)
      processor.refresh_transcript(asset)
    if not rounds:
      (asset / summary_review.NAME).unlink(missing_ok=True)  # a later round would rewrite an older draft
    else:
      problems = summary_review.check(
        target.read_text(encoding='utf-8'), asset, templates.text(template), length, pictures=pictures, review=review
      )
      summary_review.record(asset, target, review, problems, status)
  return target, pairs


def import_collection(workspace, name, text, *, guide=False, overwrite=False, source='', note=''):
  """Saves a collection overview or study guide written elsewhere, as import_summary does for one video."""
  collection.load(workspace, name)
  target = collection.text_path(workspace, name, guide)
  text = repair_links(clean(text), target.parent)
  if len(text.strip()) < 40:
    raise SummaryError('The text to import is empty or too short')
  with collection.lock(workspace, name, 'import into the collection'):
    path, _ = versions.save(target, text, source=source or '导入', note=note, make_current=overwrite)
  return path


def draft_path(workspace, video=None, *, collection=None, guide=False):
  """Where an Agent writes a summary, overview or study guide before `summarize --import` saves it: beside the file
  it becomes (so its links resolve), as <name>.draft.md; the import removes it."""
  from . import collection as collections

  target = (
    collections.text_path(workspace, collection, guide) if collection else processed(video, workspace)[2] / SUMMARY_NAME
  )
  return target.with_name(f'{target.stem}.draft.md')
