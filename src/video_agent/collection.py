"""Collections: an ordered set of related videos, such as a course, a series, a playlist or a workshop, with files of
their own (ARCHITECTURE.md, "Collections"). Generalised from yanhe-agent's course handling (user decision,
2026-10-28): nothing here assumes lectures.

A collection lives in `<workspace>/合集/<name>/`: `collection.json` (the videos in order, shared terms, skipped videos
and why), `合集总结.md` (overview) and `学习提纲.md` (study guide with self-test questions). Each video keeps its own
folder and `总结.md`; the collection's files link to them.

A collection may follow a source, such as a Bilibili season or a playlist that is still growing (user request,
2026-10-28): `collection.json` keeps its link and download folder, and `downloaded.txt` beside it is yt-dlp's download
archive, the ids already fetched, so an update downloads only the new videos and adds them at the end.
"""

import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

from . import compress, contract, corrections, files, processor

FOLDER = '合集'
DATA = 'collection.json'
OVERVIEW = '合集总结.md'
GUIDE = '学习提纲.md'
ARCHIVE = 'downloaded.txt'
# A video counts as possibly empty (a cancelled class, a recording of an empty room) when it is this short or this
# little of it is speech; the Agent or the user decides whether to skip it.
SHORT_S = 120
LITTLE_SPEECH = 0.1


class CollectionError(RuntimeError):
  pass


def _safe(name):
  cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', '_', name).strip(' .')
  if not cleaned:
    raise CollectionError(f'not a usable collection name: {name!r}')
  return cleaned


def _key(video):
  return str(Path(video).expanduser().resolve()).casefold()


def folder(workspace, name):
  return Path(workspace) / FOLDER / _safe(name)


def names(workspace):
  root = Path(workspace) / FOLDER
  return sorted(path.parent.name for path in root.glob(f'*/{DATA}')) if root.is_dir() else []


def load(workspace, name):
  path = folder(workspace, name) / DATA
  if not path.is_file():
    raise CollectionError(f'no collection {name!r} in {workspace}; create it with: video-agent collection create')
  data = json.loads(path.read_text(encoding='utf-8'))
  if data.get('schema_version', 1) > contract.COLLECTION_VERSION:
    raise CollectionError(f'collection {name!r} was written by a newer video-agent; update this one to use it')
  data.setdefault('videos', [])
  data.setdefault('terms', [])
  data.setdefault('skipped', {})
  return data


def _save(workspace, data):
  data = {'schema_version': contract.COLLECTION_VERSION, **data}
  files.write_text(folder(workspace, data['name']) / DATA, json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def _asset(workspace, video):
  return processor.asset_folder(workspace, Path(video).expanduser().resolve())


def _apply_terms(workspace, name, videos, terms):
  """Stores the collection's terms with each video; a processed one gets its cleaned transcript and context rebuilt,
  one not processed yet gets them when process rebuilds from what corrections.json holds."""
  for video in videos:
    asset = _asset(workspace, video)
    with files.video_lock(asset, 'change the collection terms'):
      corrections.set_shared(asset, name, terms)
      if not (asset / 'manifest.json').is_file():
        continue
      processor.refresh_transcript(asset)


def create(workspace, name, videos=()):
  if (folder(workspace, name) / DATA).is_file():
    raise CollectionError(f'collection {name!r} already exists')
  data = {'name': name, 'videos': [], 'terms': [], 'skipped': {}}
  _save(workspace, data)
  return add(workspace, name, videos) if videos else data


def add(workspace, name, videos, at=None):
  """Adds videos (not twice), at position `at` (0-based) or at the end, and gives them the collection's terms."""
  data = load(workspace, name)
  present = {_key(video) for video in data['videos']}
  new = []
  for video in videos:
    path = Path(video).expanduser().resolve()
    if not path.is_file():
      raise CollectionError(f'video file does not exist: {video}')
    if _key(path) not in present and str(path) not in new:
      new.append(str(path))
  position = len(data['videos']) if at is None else max(0, min(at, len(data['videos'])))
  data['videos'][position:position] = new
  _save(workspace, data)
  _apply_terms(workspace, data['name'], new, data['terms'])
  return data


def remove(workspace, name, videos):
  data = load(workspace, name)
  gone = {_key(video) for video in videos}
  kept = [video for video in data['videos'] if _key(video) not in gone]
  removed = [video for video in data['videos'] if _key(video) in gone]
  data['videos'] = kept
  data['skipped'] = {video: why for video, why in data['skipped'].items() if _key(video) not in gone}
  _save(workspace, data)
  _apply_terms(workspace, data['name'], removed, None)
  return data


def delete(workspace, name):
  """Removes the collection's own folder and its terms from the videos; the videos' folders and summaries stay."""
  data = load(workspace, name)
  _apply_terms(workspace, data['name'], data['videos'], None)
  shutil.rmtree(folder(workspace, name))


def skip(workspace, name, video, reason):
  """Marks a member as skipped with the reason (an empty reason takes the mark back)."""
  data = load(workspace, name)
  match = next((item for item in data['videos'] if _key(item) == _key(video)), None)
  if match is None:
    raise CollectionError(f'{video} is not in collection {name!r}')
  if reason:
    data['skipped'][match] = reason
  else:
    data['skipped'].pop(match, None)
  _save(workspace, data)
  return data


def set_terms(workspace, name, replace=(), remove=()):
  """Changes the shared terms and applies them to every processed member."""
  data = load(workspace, name)
  gone = set(remove)
  terms = [pair for pair in data['terms'] if pair[0] not in gone]
  for wrong, right in replace:
    terms = [pair for pair in terms if pair[0] != wrong] + [[wrong, right]]
  data['terms'] = terms
  _save(workspace, data)
  _apply_terms(workspace, data['name'], data['videos'], terms)
  return data


def status(workspace, name) -> contract.Collection:
  """The collection with one entry per video: whether it is processed and summarized, its length, how much of it is
  speech, whether it may be empty, and whether it was skipped; and which videos' summaries changed after the overview
  and the study guide were written (`overview_behind`, `guide_behind`), so they can be brought up to date."""
  data = load(workspace, name)
  members: list[contract.Member] = []
  for index, video in enumerate(data['videos'], 1):
    asset = _asset(workspace, video)
    manifest_path = asset / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.is_file() else None
    rows = corrections.rows_in_use(asset) or []
    length = manifest['duration_s'] if manifest else None
    speech = sum(max(0.0, end - start) for start, end, _ in rows)
    share = speech / length if length else None
    members.append(
      {
        'index': index,
        'video': video,
        'name': Path(video).stem,
        'folder': str(asset),
        'processed': manifest is not None,
        'summary': str(asset / '总结.md') if (asset / '总结.md').is_file() else None,
        'duration_s': length,
        'speech_share': round(share, 3) if share is not None else None,
        'maybe_empty': length is not None and (length < SHORT_S or (share or 0) < LITTLE_SPEECH),
        'skipped': data['skipped'].get(video),
        'compression': compress.known(video)[1] if Path(video).is_file() else None,  # the cache only
      }
    )
  place = folder(workspace, name)

  def behind(path):
    """The videos whose summary changed after the overview or study guide was written, by index."""
    if not path.is_file():
      return []
    written = path.stat().st_mtime
    return [
      member['index'] for member in members if member['summary'] and Path(member['summary']).stat().st_mtime > written
    ]

  return {
    'name': data['name'],
    'folder': str(place),
    'overview': str(place / OVERVIEW) if (place / OVERVIEW).is_file() else None,
    'guide': str(place / GUIDE) if (place / GUIDE).is_file() else None,
    'overview_behind': behind(place / OVERVIEW),
    'guide_behind': behind(place / GUIDE),
    'terms': data['terms'],
    'source': data.get('source'),
    'videos': members,
  }


def archive(workspace, name):
  """yt-dlp's download archive for the collection's source: one line per video id already fetched."""
  return folder(workspace, name) / ARCHIVE


def follow(workspace, name, url, download_folder, auto=False):
  """Remembers where the collection's videos come from, so `update` can fetch the ones added there later."""
  data = load(workspace, name)
  old = data.get('source') or {}
  data['source'] = {
    'url': url,
    'folder': str(Path(download_folder).expanduser().resolve()),
    'auto': bool(auto),
    'checked': old.get('checked') if old.get('url') == url else None,
    'new': old.get('new', 0) if old.get('url') == url else 0,
  }
  _save(workspace, data)
  return data


def unfollow(workspace, name):
  data = load(workspace, name)
  data.pop('source', None)
  _save(workspace, data)
  archive(workspace, name).unlink(missing_ok=True)
  return data


def set_auto(workspace, name, auto):
  data = load(workspace, name)
  if not data.get('source'):
    raise CollectionError(f'collection {name!r} follows no source; set one with: video-agent collection follow')
  data['source']['auto'] = bool(auto)
  _save(workspace, data)
  return data


def checked(workspace, name, saved):
  """Records an update: adds what it saved at the end (members already there stay where they are) and notes when it
  ran and how many videos it added."""
  before = len(load(workspace, name)['videos'])
  data = add(workspace, name, saved) if saved else load(workspace, name)
  if data.get('source'):
    data['source']['checked'] = datetime.now(UTC).isoformat(timespec='seconds')
    data['source']['new'] = len(data['videos']) - before
    _save(workspace, data)
  return data


def lock(workspace, name, action):
  """One writer of the collection's own files at a time, as for a video's folder."""
  return files.video_lock(folder(workspace, name), action)
