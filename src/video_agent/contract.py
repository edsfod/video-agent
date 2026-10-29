"""What the CLI prints with `--json` and what it keeps in `manifest.json` and `collection.json`: the contract between the
CLI and the programs that read it, the desktop app first (docs/decisions/front-end-types.md).

The types are checked three ways: mypy checks the functions that build them; the tests check every JSON value the CLI
prints against its type (`check`, switched on in tests/conftest.py); and `scripts/cli_types.py` writes them as
TypeScript for the app (`gui/src/cli-types.d.ts`), which a test keeps up to date. A field the app reads is added here
first. JSON_VERSION goes up when a field is removed or changes meaning, not when one is added; COLLECTION_VERSION when
collection.json changes so that an older CLI would misread it.
"""

import types
import typing
from typing import Any, Literal, NotRequired, TypedDict

JSON_VERSION = 1
COLLECTION_VERSION = 1

Region = list[int]  # x, y, width, height
Pair = list[str]  # wrong, right
CompressionState = Literal['compressed', 'efficient', 'not-smaller'] | None


class Tools(TypedDict):
  """`tools --json`: where each program comes from, None when missing, and the version of this contract."""

  json_version: int
  ffmpeg: str | None
  ffprobe: str | None
  yt_dlp: str | None
  slide_extractor: str | None


class Config(TypedDict):
  """`config --json`."""

  provider: str
  model: str | None
  base_url: str
  key: str | None  # where the key is: 'Credential Manager', an environment variable's name, or None
  settings: str


# manifest.json. Fields added after 0.1.0 are NotRequired: a video processed by an older version lacks them until it
# is processed again.


class Stream(TypedDict):
  index: int | None
  type: str | None
  codec: str | None
  language: str | None


class TranscriptEntry(TypedDict):
  source: str  # 'sidecar:<file>', 'embedded:<language>', 'file:<file>', 'bcut-remote' or 'unavailable'
  segments: int
  error: str | None
  srt: str | None
  clean: NotRequired[str | None]
  corrections: NotRequired[int]


class Picture(TypedDict):
  time_s: float
  path: str  # relative to the video's folder, with /


class PointedFrame(Picture):
  text: str


class Layout(TypedDict):
  kind: Literal['screen', 'split', 'inset', 'camera']
  size: list[int]
  screen: Region | None
  camera: Region | None
  activity: list[float]
  picture: str | None
  given: bool
  warning: str | None


class Options(TypedDict):
  frame_interval: float
  scene_threshold: float
  max_frames: int | None


class Limits(TypedDict):
  frames: int
  frames_found: int
  pages: int
  pages_found: int
  page_shown_at_least_s: float


class SlideExtraction(TypedDict):
  enabled: bool
  imported: NotRequired[str | None]
  output: str | None
  timeline: str | None
  error: str | None
  slides: list[Picture]


class Manifest(TypedDict):
  schema_version: int
  source_video: str
  updated_utc: str
  duration_s: float
  streams: list[Stream]
  transcript: TranscriptEntry
  representative_frame_run: str
  layout: NotRequired[Layout]
  pointed_frames: NotRequired[list[PointedFrame]]
  options: NotRequired[Options]
  screen_pages: NotRequired[list[Picture]]
  limits: NotRequired[Limits]
  representative_frames: list[Picture]
  slide_extraction: SlideExtraction
  summary_context: str
  summary_generated: bool


class Show(TypedDict):
  """`show`: a video's processing folder, without changing anything."""

  video: str
  duration_s: float
  folder: str
  processed: bool
  manifest: Manifest | None
  summary: str | None
  context: str | None
  transcript: str | None  # the transcript in use: the cleaned one when there are corrections
  transcript_original: str | None
  corrections: list[Pair]
  extra_frames: list[str]
  subtitles: str | None  # where processing would take subtitles from: a file's label, 'embedded', or None
  compression: CompressionState


class Processed(TypedDict):
  """`process --json`, one line per video that was processed."""

  video: str
  asset: str
  rows: int
  frames: int
  slides: int
  transcript_error: str | None
  slide_error: str | None
  source: str
  reused: NotRequired[bool]  # processed before with the same settings, so used as it was


class Failed(TypedDict):
  """A line for a video that failed, from `process --json` and `compress --json`."""

  video: str
  error: str


class Saved(TypedDict):
  """`download --json` and `collection update --json`, one line per saved file; `new` is false for a file that was
  there already."""

  path: str
  new: bool


class Playlist(TypedDict):
  url: str
  title: str
  count: int
  titles: list[str]  # the first entries' titles; Bilibili's lists give none


class PlaylistFound(TypedDict):
  """`download --json` for a link that stands for a list, downloaded only with --playlist."""

  playlist: Playlist


class Change(TypedDict):
  time: str
  before: str
  after: str


class Fixed(TypedDict):
  """`fix --json`."""

  corrections: list[Pair]
  unmatched: list[str]
  changed_lines: int
  changes: list[Change]


class Checked(TypedDict):
  """`compress --check --json`, one line per video."""

  video: str
  state: CompressionState


class Compressed(TypedDict):
  """`compress --json`, one line per video; `skipped` says why it was left as it was."""

  video: str
  skipped: str | None
  before: int
  after: int
  still: bool | None


class Version(TypedDict):
  file: str
  created: str
  source: str
  note: str
  path: str


class Versions(TypedDict):
  """`versions --json`: the current text and the others, newest first."""

  current: Version | None
  versions: list[Version]


class Template(TypedDict):
  """`template --list` (a list of these), and `template NAME --info|--use|--edit|--accept|--reset|--copy NEW`."""

  name: str
  path: str
  builtin: bool
  customized: bool
  outdated: bool
  default: str | None
  current: bool


class TemplateDeleted(TypedDict):
  """`template NAME --reset` for a template of the user's own."""

  name: str
  deleted: bool


# collection.json and `collection ... --json`.


class Source(TypedDict):
  """The list a collection follows."""

  url: str
  folder: str
  auto: bool
  checked: str | None
  new: int


class CollectionData(TypedDict):
  """collection.json. Files written before 1.0.1 have no schema_version."""

  schema_version: NotRequired[int]
  name: str
  videos: list[str]
  terms: list[Pair]
  skipped: dict[str, str]
  source: NotRequired[Source | None]


class Member(TypedDict):
  index: int
  video: str
  name: str
  folder: str
  processed: bool
  summary: str | None
  duration_s: float | None
  speech_share: float | None
  maybe_empty: bool
  skipped: str | None
  compression: CompressionState


class Collection(TypedDict):
  """`collection NAME <action>` and `collection list` (a list of these)."""

  name: str
  folder: str
  overview: str | None
  guide: str | None
  overview_behind: list[int]
  guide_behind: list[int]
  terms: list[Pair]
  source: Source | None
  videos: list[Member]


class Inspected(TypedDict):
  """`inspect`: ffprobe's streams as they come."""

  path: str
  duration_s: float
  streams: list[dict[str, Any]]


# What each command prints. A command that prints several lines lists the types a line may have.
OUTPUTS: dict[str, Any] = {
  'tools': Tools,
  'config': Config,
  'show': Show,
  'inspect': Inspected,
  'process': Processed | Failed,
  'download': Saved | PlaylistFound,
  'fix': Fixed,
  'compress': Compressed | Checked | Failed,
  'versions': Versions,
  'template': Template | TemplateDeleted | list[Template],
  'collection': Collection | list[Collection] | Saved,
  'models': list[str],
}

CHECK = False  # set by the tests: every printed value is checked against its type


class ContractError(AssertionError):
  pass


def check(value, shape, where='value'):
  """Raises ContractError where `value` does not have the type `shape`. A TypedDict must have its required keys and
  no others."""
  if shape is Any:
    return
  if shape is None or shape is type(None):
    if value is not None:
      raise ContractError(f'{where}: expected null, got {value!r}')
    return
  origin = typing.get_origin(shape)
  if origin in (typing.Union, types.UnionType):
    errors = []
    for option in typing.get_args(shape):
      try:
        check(value, option, where)
        return
      except ContractError as error:
        errors.append(str(error))
    raise ContractError(' / '.join(errors))
  if origin is Literal:
    if value not in typing.get_args(shape):
      raise ContractError(f'{where}: {value!r} is not one of {typing.get_args(shape)}')
    return
  if origin is list:
    if not isinstance(value, list):
      raise ContractError(f'{where}: expected a list, got {value!r}')
    (item,) = typing.get_args(shape)
    for index, entry in enumerate(value):
      check(entry, item, f'{where}[{index}]')
    return
  if origin is dict:
    if not isinstance(value, dict):
      raise ContractError(f'{where}: expected an object, got {value!r}')
    _, item = typing.get_args(shape)
    for key, entry in value.items():
      check(entry, item, f'{where}.{key}')
    return
  if typing.is_typeddict(shape):
    if not isinstance(value, dict):
      raise ContractError(f'{where}: expected {shape.__name__}, got {value!r}')
    fields = typing.get_type_hints(shape)
    missing = shape.__required_keys__ - value.keys()
    extra = value.keys() - fields.keys()
    if missing or extra:
      raise ContractError(f'{where}: {shape.__name__} lacks {sorted(missing)}, has extra {sorted(extra)}')
    for key, entry in value.items():
      check(entry, fields[key], f'{where}.{key}')
    return
  if shape is float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
      raise ContractError(f'{where}: expected a number, got {value!r}')
    return
  if shape is int and isinstance(value, bool) or not isinstance(value, shape):
    raise ContractError(f'{where}: expected {shape.__name__}, got {value!r}')
