"""Command-line interface for local video evidence preparation and optional downloads."""

import argparse
import getpass
import json
import sys
from pathlib import Path

from . import collection, corrections, files, processor, settings
from . import summarize as summaries
from .download import DownloadError, download_urls
from .media import MediaError, duration, parse_clock, probe, save_frame
from .processor import asset_folder, process_video
from .summarize import import_summary, material, pack, summarize_video, template
from .transcript import format_clock as transcript_clock

# Where the window saves downloads in a workspace, and so where a followed list's new videos go by default.
DOWNLOADS = '下载'


def positive_float(value):
  number = float(value)
  if number <= 0:
    raise argparse.ArgumentTypeError('must be greater than zero')
  return number


def positive_int(value):
  number = int(value)
  if number < 1:
    raise argparse.ArgumentTypeError('must be at least 1')
  return number


def count_value(value):
  number = int(value)
  if number < 0:
    raise argparse.ArgumentTypeError('must be 0 or more')
  return number


def threshold_value(value):
  number = float(value)
  if not 0 < number <= 1:
    raise argparse.ArgumentTypeError('must be greater than 0 and at most 1')
  return number


def clock_value(value):
  try:
    return parse_clock(value)
  except ValueError:
    raise argparse.ArgumentTypeError('use seconds, MM:SS or HH:MM:SS') from None


def build_parser():
  parser = argparse.ArgumentParser(
    prog='video-agent',
    description='Prepare local videos for transcription and summarization; downloading is optional.',
  )
  commands = parser.add_subparsers(dest='command', required=True)

  download = commands.add_parser('download', help='optionally download URLs to local video files with yt-dlp')
  download.add_argument('urls', nargs='+', help='URL(s) supported by yt-dlp')
  download.add_argument('-o', '--output', type=Path, default=Path.cwd() / 'video-agent-downloads')
  download.add_argument(
    '--format', dest='format_selector', default='bv*+ba/b', help='yt-dlp format selector (default: bv*+ba/b)'
  )
  download.add_argument('--playlist', action='store_true', help='download playlists; default is one video only')
  download.add_argument(
    '--no-subs', action='store_true', help="don't save the site's subtitle tracks beside the video (saved by default)"
  )
  download.add_argument(
    '--cookies', type=Path, help='Netscape cookies file for yt-dlp; Bilibili shows subtitles only to logged-in users'
  )
  download.add_argument('--yt-dlp', type=Path, help='path to yt-dlp executable')
  download.add_argument('--yt-dlp-config', type=Path, help='explicit yt-dlp config file; other configs are ignored')
  download.add_argument('--json', action='store_true', help='print one JSON object per saved file; progress to stderr')
  download.add_argument(
    '--collection',
    metavar='NAME',
    help='add the saved files, in order, to this collection of --workspace (made if missing); for playlists and series',
  )
  download.add_argument(
    '--workspace',
    type=Path,
    default=Path.cwd() / 'video-agent-output',
    help='the workspace that holds --collection (default: video-agent-output)',
  )
  download.add_argument(
    '--follow',
    action='store_true',
    help='with --playlist and --collection: remember the list, so `collection update` fetches its new videos later',
  )
  download.add_argument('--auto', action='store_true', help='with --follow: let the window check the list on its own')

  inspect = commands.add_parser('inspect', help='inspect streams and duration without changing the video')
  inspect.add_argument('video', type=Path)

  process = commands.add_parser('process', help='prepare subtitles, representative frames, and Agent-ready context')
  process.add_argument('videos', nargs='+', type=Path)
  process.add_argument('--json', action='store_true', help='print one JSON object per video; progress to stderr')
  process.add_argument('-o', '--output', type=Path, default=Path.cwd() / 'video-agent-output')
  process.add_argument(
    '--frame-interval', type=positive_float, default=60, help='seconds between regular visual samples (default: 60)'
  )
  process.add_argument(
    '--scene-threshold', type=threshold_value, default=0.35, help='scene-change sensitivity from 0 to 1 (default: 0.35)'
  )
  process.add_argument(
    '--max-frames',
    type=positive_int,
    help='at most this many representative frames per video (default: as many as the video has, up to 500)',
  )
  process.add_argument(
    '--screen-region',
    metavar='X,Y,W,H',
    help='the screen part of the frame, in pixels, when the detected layout is wrong (see layout.jpg)',
  )
  process.add_argument(
    '--extract-slides', action='store_true', help='run AutoSlides Extractor and save slide images; off by default'
  )
  process.add_argument(
    '--slide-extractor',
    type=Path,
    help='path to AutoSlidesExtractor.exe; otherwise search PATH and standard install locations',
  )
  process.add_argument(
    '--asr',
    choices=('none', 'bcut'),
    default='none',
    help='transcription provider when no local subtitle exists (default: none)',
  )
  process.add_argument(
    '--allow-remote-asr',
    action='store_true',
    help='allow sending extracted audio to Bilibili BCut; requires --asr bcut',
  )
  process.add_argument(
    '--overwrite-transcript', action='store_true', help='replace an existing transcript with newly selected source data'
  )
  frame = commands.add_parser('frame', help="save frames at chosen times into the video's processing workspace")
  frame.add_argument('video', type=Path)
  frame.add_argument('times', nargs='+', type=clock_value, help='seconds, MM:SS or HH:MM:SS')
  frame.add_argument(
    '-o',
    '--output',
    type=Path,
    default=Path.cwd() / 'video-agent-output',
    help='the workspace passed to process (default: video-agent-output)',
  )

  summarize = commands.add_parser('summarize', help='optionally write 总结.md with a model API from processed evidence')
  summarize.add_argument('video', type=Path, nargs='?', help='the video; leave out with --collection')
  summarize.add_argument(
    '--collection', metavar='NAME', help="write the collection overview (合集总结.md) from its videos' summaries"
  )
  summarize.add_argument('--guide', action='store_true', help='with --collection: write the study guide (学习提纲.md)')
  summarize.add_argument(
    '-o',
    '--output',
    type=Path,
    default=Path.cwd() / 'video-agent-output',
    help='the workspace passed to process (default: video-agent-output)',
  )
  summarize.add_argument('--provider', choices=tuple(settings.PROVIDERS), help='default: the one set with config')
  summarize.add_argument('--model', help='default: the one set with config')
  summarize.add_argument('--base-url', help='API base URL, such as http://127.0.0.1:11434/v1 for Ollama')
  summarize.add_argument('--request', default='', help="the user's wishes for this summary, passed to the model")
  summarize.add_argument(
    '--max-images',
    type=positive_int,
    default=60,
    help='images sent with the first request; screen pages go on contact sheets when they need more (default: 60)',
  )
  summarize.add_argument(
    '--max-extra-frames',
    type=count_value,
    default=8,
    help='frames the model may ask for through tool calling (default: 8)',
  )
  summarize.add_argument('--no-tools', action='store_true', help='for models without tool calling')
  summarize.add_argument('--overwrite', action='store_true', help='replace an existing 总结.md')
  summarize.add_argument(
    '--import',
    dest='import_from',
    metavar='FILE',
    help='save a summary written elsewhere (a file, or - for stdin) as 总结.md instead of calling a model',
  )

  packing = commands.add_parser(
    'pack', help='the summary prompt for a chat AI: print it, or zip it with the frames (--zip)'
  )
  packing.add_argument('video', type=Path, nargs='?', help='the video; leave out with --collection')
  packing.add_argument('--collection', metavar='NAME', help="print the prompt for the collection's overview")
  packing.add_argument('--guide', action='store_true', help='with --collection: for the study guide instead')
  packing.add_argument(
    '-o',
    '--output',
    type=Path,
    default=Path.cwd() / 'video-agent-output',
    help='the workspace passed to process (default: video-agent-output)',
  )
  packing.add_argument('--request', default='', help="the user's wishes for this summary")
  packing.add_argument('--zip', type=Path, help='write 提示词.md and the frames into this zip file')
  packing.add_argument(
    '--max-images',
    type=positive_int,
    default=40,
    help='whole frames put into the zip besides every screen page (default: 40)',
  )

  config = commands.add_parser('config', help='show or change the summarize provider, model, base URL and API key')
  config.add_argument('--provider', choices=tuple(settings.PROVIDERS), help='choose the provider to use and edit')
  config.add_argument('--model')
  config.add_argument('--base-url')
  keys = config.add_mutually_exclusive_group()
  keys.add_argument('--set-key', action='store_true', help='read an API key and save it in Windows Credential Manager')
  keys.add_argument('--delete-key', action='store_true', help='remove the saved API key')
  config.add_argument('--json', action='store_true', help='print the resulting settings as JSON')

  grouping = commands.add_parser(
    'collection', help='group related videos (a course, a series, a playlist) for an overview and a study guide'
  )
  actions = grouping.add_subparsers(dest='action', required=True)

  def workspace_option(parser):
    parser.add_argument(
      '-o',
      '--output',
      type=Path,
      default=Path.cwd() / 'video-agent-output',
      help='the workspace passed to process (default: video-agent-output)',
    )

  for action, text in (
    ('create', 'make a collection, optionally with videos'),
    ('add', 'add videos, at the end or at --at'),
    ('remove', 'take videos out (their folders and summaries stay)'),
    ('show', 'each video with its state: processed, summarized, length, share of speech, maybe empty, skipped'),
    ('delete', "remove the collection's own folder (the videos' folders and summaries stay)"),
    ('skip', 'mark a video as skipped, with --reason (an empty reason takes it back)'),
    ('terms', "shared corrections, applied to every video's cleaned transcript"),
    ('list', 'the collections in the workspace'),
    ('follow', 'remember the list the videos come from (a series, a season, a playlist), or turn --auto on or off'),
    ('unfollow', 'forget the list; the videos stay'),
    ('update', "download the followed list's new videos and add them at the end"),
  ):
    sub = actions.add_parser(action, help=text)
    if action != 'list':
      sub.add_argument('name')
    if action in ('create', 'add', 'remove'):
      sub.add_argument('videos', type=Path, nargs='*' if action == 'create' else '+')
    if action == 'add':
      sub.add_argument('--at', type=positive_int, metavar='N', help='insert before the Nth video (1 = first)')
    if action == 'skip':
      sub.add_argument('video', type=Path)
      sub.add_argument('--reason', default='skipped', help='why, as shown in the overview; empty to take it back')
    if action == 'terms':
      sub.add_argument('--replace', nargs=2, action='append', default=[], metavar=('WRONG', 'RIGHT'))
      sub.add_argument('--remove', action='append', default=[], metavar='WRONG')
    if action == 'follow':
      sub.add_argument('url', nargs='?', help='the list; leave out to change --auto only')
      sub.add_argument('--folder', type=Path, help='where new videos are saved (default: <workspace>/下载)')
      sub.add_argument(
        '--auto',
        action=argparse.BooleanOptionalAction,
        help='whether the window checks the list on its own while it runs',
      )
    if action == 'update':
      sub.add_argument('--cookies', type=Path, help='Netscape cookies file for yt-dlp (Bilibili subtitles)')
      sub.add_argument('--no-subs', action='store_true', help="don't save the site's subtitle tracks")
      sub.add_argument('--yt-dlp', type=Path, help='path to yt-dlp executable')
      sub.add_argument('--yt-dlp-config', type=Path, help='explicit yt-dlp config file; other configs are ignored')
      sub.add_argument('--json', action='store_true', help='one JSON object per saved file, then the collection')
    workspace_option(sub)

  fixing = commands.add_parser(
    'fix',
    help='correct recurring mishearings: the original transcript stays, transcript.clean.* is used from then on',
  )
  fixing.add_argument('video', type=Path)
  fixing.add_argument(
    '-o',
    '--output',
    type=Path,
    default=Path.cwd() / 'video-agent-output',
    help='the workspace passed to process (default: video-agent-output)',
  )
  fixing.add_argument(
    '--replace',
    nargs=2,
    action='append',
    default=[],
    metavar=('WRONG', 'RIGHT'),
    help='replace WRONG with RIGHT throughout the transcript; a Latin word matches as a whole word only',
  )
  fixing.add_argument('--remove', action='append', default=[], metavar='WRONG', help='take a correction back')
  fixing.add_argument('--reset', action='store_true', help='remove every correction and the cleaned transcript')
  fixing.add_argument('--json', action='store_true', help='print the corrections and the changed lines as JSON')

  show = commands.add_parser('show', help="print JSON about a video's processing folder without changing anything")
  show.add_argument('video', type=Path)
  show.add_argument(
    '-o',
    '--output',
    type=Path,
    default=Path.cwd() / 'video-agent-output',
    help='the workspace passed to process (default: video-agent-output)',
  )

  rules = commands.add_parser(
    'template', help='print the summary rules and template every route follows (your copy, if you made one)'
  )
  choice = rules.add_mutually_exclusive_group()
  choice.add_argument('--default', action='store_true', help='print the built-in default instead of your copy')
  choice.add_argument('--edit', action='store_true', help='make your own copy (once) and print its path as JSON')
  choice.add_argument('--reset', action='store_true', help='delete your copy and go back to the default')
  choice.add_argument('--accept', action='store_true', help="mark your copy as up to date with the default's changes")
  choice.add_argument('--info', action='store_true', help='print as JSON where your copy is and whether it is outdated')
  return parser


def _config(args):
  data = settings.load()
  name = args.provider or data['provider']
  entry = data['providers'].setdefault(name, {})
  changed = bool(args.provider and args.provider != data['provider'])
  data['provider'] = name
  for field in ('model', 'base_url'):
    value = getattr(args, field)
    if value:
      entry[field] = value.rstrip('/') if field == 'base_url' else value
      changed = True
  if changed:
    settings.save(data)
  if args.set_key:
    key = getpass.getpass(f'API key for {name}: ') if sys.stdin.isatty() else sys.stdin.readline().strip()
    if not key:
      print('No key entered; nothing saved')
      return 1
    settings.set_key(name, key)
  if args.delete_key:
    print('Key deleted' if settings.delete_key(name) else 'No saved key')
  defaults = settings.PROVIDERS[name]
  shown = {
    'provider': name,
    'model': entry.get('model') or defaults['model'],
    'base_url': entry.get('base_url') or defaults['base_url'],
    'key': settings.key_source(name),
    'settings': str(settings.settings_path()),
  }
  if args.json:
    _emit(shown)
    return 0
  print(f'provider: {name}')
  print(f'model:    {shown["model"] or "(not set; pass --model)"}')
  print(f'base URL: {shown["base_url"]}')
  print(f'API key:  {shown["key"] or "none"}')
  print(f'settings: {shown["settings"]}')
  return 0


def _progress(args):
  """Status lines go to stdout normally, and to stderr when --json keeps stdout for results."""
  if getattr(args, 'json', False):
    return lambda message: print(message, file=sys.stderr, flush=True)
  return print


def _emit(value):
  print(json.dumps(value, ensure_ascii=False), flush=True)


def _show(args):
  video, info = probe(args.video)
  asset = asset_folder(args.output, video)
  manifest = asset / 'manifest.json'

  def existing(name):
    path = asset / name
    return str(path) if path.is_file() else None

  _emit(
    {
      'video': str(video),
      'duration_s': duration(info),
      'folder': str(asset),
      'processed': manifest.is_file(),
      'manifest': json.loads(manifest.read_text(encoding='utf-8')) if manifest.is_file() else None,
      'summary': existing('总结.md'),
      'context': existing('summary-context.md'),
      'transcript': str(corrections.in_use(asset)) if corrections.in_use(asset) else None,
      'transcript_original': existing('transcript.txt'),
      'corrections': [list(pair) for pair in corrections.load(asset)],
      'extra_frames': sorted(str(path) for path in (asset / 'frames' / 'extra').glob('frame-*.jpg')),
    }
  )
  return 0


def _collection(args):
  workspace, action = args.output, args.action
  if action == 'list':
    _emit([collection.status(workspace, name) for name in collection.names(workspace)])
    return 0
  if action == 'create':
    collection.create(workspace, args.name, args.videos)
  elif action == 'add':
    collection.add(workspace, args.name, args.videos, at=args.at - 1 if args.at else None)
  elif action == 'remove':
    collection.remove(workspace, args.name, args.videos)
  elif action == 'delete':
    collection.delete(workspace, args.name)
    print(f'deleted collection {args.name}')
    return 0
  elif action == 'skip':
    collection.skip(workspace, args.name, args.video, args.reason)
  elif action == 'terms':
    collection.set_terms(workspace, args.name, args.replace, args.remove)
  elif action == 'follow':
    if args.url:
      where = args.folder or Path(workspace) / DOWNLOADS
      collection.follow(workspace, args.name, args.url, where, auto=bool(args.auto))
    elif args.auto is not None:
      collection.set_auto(workspace, args.name, args.auto)
    else:
      print('collection follow: give the list URL, or --auto / --no-auto')
      return 2
  elif action == 'unfollow':
    collection.unfollow(workspace, args.name)
  elif action == 'update':
    return _update(args)
  _emit(collection.status(workspace, args.name))
  return 0


def _update(args):
  workspace, name = args.output, args.name
  source = collection.load(workspace, name).get('source')
  if not source:
    print(f'collection {name} follows no list; set one with: video-agent collection follow {name} <URL>')
    return 1
  try:
    paths, failures = download_urls(
      [source['url']],
      source['folder'],
      playlist=True,
      subtitles=not args.no_subs,
      executable_path=args.yt_dlp,
      config_path=args.yt_dlp_config,
      cookies_path=args.cookies,
      status=_progress(args),
      archive_path=collection.archive(workspace, name),
    )
  except DownloadError as error:
    print(f'collection update: ERROR: {error}')
    return 1
  for path in paths:
    if args.json:
      _emit({'path': str(path)})
  data = collection.checked(workspace, name, paths)
  print(f'{data["source"]["new"]} new videos in collection {name}', file=sys.stderr)
  if args.json:
    _emit(collection.status(workspace, name))
  # yt-dlp reports a failure for one entry of a list as a failure of the whole run; what it saved is kept.
  return 1 if failures and not paths else 0


def _fix(args):
  video, _ = probe(args.video)
  asset = asset_folder(args.output, video)
  manifest_path = asset / 'manifest.json'
  if corrections.original_rows(asset) is None or not manifest_path.is_file():
    print(f'{video.name} has no transcript in {args.output}; run process with the same --output first')
    return 1
  with files.video_lock(asset, 'fix'):
    removed = set(args.remove)
    pairs = [] if args.reset else [pair for pair in corrections.load(asset) if pair[0] not in removed]
    for wrong, right in args.replace:
      pairs = [pair for pair in pairs if pair[0] != wrong] + [(wrong, right)]
    corrections.save(asset, pairs)
    changes = corrections.rebuild(asset)
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    told = manifest['transcript']
    manifest['transcript'] = processor.transcript_entry(asset, told['source'], told['segments'], told.get('error'))
    processor._write_json(manifest_path, manifest)
    processor.write_context(asset)
  text = ' '.join(row[2] for row in corrections.original_rows(asset))
  unmatched = [wrong for wrong, _ in args.replace if not corrections._pattern(wrong).search(text)]
  if args.json:
    _emit(
      {
        'corrections': [list(pair) for pair in pairs],
        'unmatched': unmatched,
        'changed_lines': len(changes),
        'changes': [
          {'time': transcript_clock(start), 'before': before, 'after': after} for start, before, after in changes
        ],
      }
    )
    return 0
  for start, before, after in changes[:40]:
    print(f'[{transcript_clock(start)}] {before}\n           {after}')
  if len(changes) > 40:
    print(f'... and {len(changes) - 40} more changed lines')
  for wrong in unmatched:
    print(f'not found in the transcript: {wrong}')
  print(
    f'{len(pairs)} corrections, {len(changes)} changed lines' + (', cleaned transcript removed' if not pairs else '')
  )
  return 0


def run(args):
  if args.command == 'download':
    following = args.follow and args.collection and args.playlist and len(args.urls) == 1
    if args.follow and not following:
      print('download: --follow needs --playlist, --collection and exactly one URL')
      return 2
    if following:
      # Made first, so the download archive has its folder and records this first download.
      if not (collection.folder(args.workspace, args.collection) / collection.DATA).is_file():
        collection.create(args.workspace, args.collection)
      collection.follow(args.workspace, args.collection, args.urls[0], args.output, auto=args.auto)
    try:
      paths, failures = download_urls(
        args.urls,
        args.output,
        format_selector=args.format_selector,
        playlist=args.playlist,
        subtitles=not args.no_subs,
        executable_path=args.yt_dlp,
        config_path=args.yt_dlp_config,
        cookies_path=args.cookies,
        status=_progress(args),
        found_list=(lambda found: _emit({'playlist': found})) if args.json else None,
        archive_path=collection.archive(args.workspace, args.collection) if following else None,
      )
    except DownloadError as error:
      print(f'download: ERROR: {error}')
      return 1
    for path in paths:
      if args.json:
        _emit({'path': str(path)})
      else:
        print(f'Next: process this local file separately: {path}')
    if following:
      collection.checked(args.workspace, args.collection, paths)
      print(f'added {len(paths)} videos to collection {args.collection}, which follows the list', file=sys.stderr)
    elif args.collection and paths:
      if not (collection.folder(args.workspace, args.collection) / collection.DATA).is_file():
        collection.create(args.workspace, args.collection)
      collection.add(args.workspace, args.collection, paths)
      print(f'added {len(paths)} videos to collection {args.collection}', file=sys.stderr)
    return 1 if failures else 0

  if args.command == 'inspect':
    video, info = probe(args.video)
    print(
      json.dumps(
        {'path': str(video), 'duration_s': duration(info), 'streams': info.get('streams', [])},
        ensure_ascii=False,
        indent=2,
      )
    )
    return 0

  if args.command == 'fix':
    return _fix(args)

  if args.command == 'show':
    return _show(args)

  if args.command == 'template':
    action = {'edit': summaries.edit_template, 'reset': summaries.reset_template}
    action |= {'accept': summaries.accept_template, 'info': summaries.template_info}
    chosen = next((name for name in action if getattr(args, name)), None)
    if chosen:
      _emit(action[chosen]())
    else:
      sys.stdout.write(summaries.default_template() if args.default else template())
      if not args.default and summaries.template_info()['outdated']:
        print(
          'Note: your summary rules were copied from an older default; compare with template --default', file=sys.stderr
        )
    return 0

  if args.command == 'config':
    return _config(args)

  if args.command == 'collection':
    return _collection(args)

  if args.command in ('summarize', 'pack') and not args.video and not args.collection:
    print(f'{args.command}: give a video or --collection NAME')
    return 2

  if args.command == 'summarize' and args.import_from:
    # Bytes, not text: the GUI sends UTF-8, whatever code page a frozen build would decode stdin with.
    source = sys.stdin.buffer.read() if args.import_from == '-' else Path(args.import_from).read_bytes()
    text = source.decode('utf-8-sig')
    if args.collection:
      target = summaries.import_collection(
        args.output, args.collection, text, guide=args.guide, overwrite=args.overwrite
      )
    else:
      target = import_summary(args.video, args.output, text, overwrite=args.overwrite)
    print(target)
    return 0

  if args.command == 'pack' and args.collection:
    sys.stdout.write(
      summaries.collection_material(args.output, args.collection, guide=args.guide, request=args.request)
    )
    return 0

  if args.command == 'summarize' and args.collection:
    chosen = settings.resolve(args.provider, args.model, args.base_url)
    print(
      summaries.summarize_collection(
        args.output,
        args.collection,
        chosen,
        settings.get_key(chosen['provider']),
        guide=args.guide,
        request=args.request,
        overwrite=args.overwrite,
      )
    )
    return 0

  if args.command == 'pack':
    if args.zip:
      target, count = pack(args.video, args.output, args.zip, request=args.request, max_images=args.max_images)
      print(f'{target} ({count} pictures)')
    else:
      sys.stdout.write(material(args.video, args.output, request=args.request)[0])
    return 0

  if args.command == 'summarize':
    chosen = settings.resolve(args.provider, args.model, args.base_url)
    path = summarize_video(
      args.video,
      args.output,
      chosen,
      settings.get_key(chosen['provider']),
      request=args.request,
      max_images=args.max_images,
      max_extra_frames=args.max_extra_frames,
      use_tools=not args.no_tools,
      overwrite=args.overwrite,
    )
    print(path)
    return 0

  if args.command == 'frame':
    video, info = probe(args.video)
    length = duration(info)
    asset = asset_folder(args.output, video)
    failures = 0
    for second in args.times:
      try:
        print(save_frame(video, asset, second, length))
      except MediaError as error:
        print(f'{second:g}s: ERROR: {error}')
        failures += 1
    return 1 if failures else 0

  if args.allow_remote_asr and args.asr != 'bcut':
    raise ValueError('--allow-remote-asr requires --asr bcut')
  failures = 0
  say = _progress(args)
  for video in args.videos:
    try:
      result = process_video(
        video,
        args.output,
        interval=args.frame_interval,
        scene_threshold=args.scene_threshold,
        max_frames=args.max_frames,
        screen_region=args.screen_region,
        extract_slides=args.extract_slides,
        slide_extractor_path=args.slide_extractor,
        asr=args.asr,
        allow_remote_asr=args.allow_remote_asr,
        overwrite=args.overwrite_transcript,
        status=say,
      )
    except (OSError, MediaError, RuntimeError, ValueError) as error:
      if args.json:
        _emit({'video': str(video), 'error': str(error)})
      else:
        print(f'{video}: ERROR: {error}')
      failures += 1
      continue
    failures += bool(result['transcript_error']) + bool(result['slide_error'])
    if args.json:
      _emit({'video': str(video), **result, 'asset': str(result['asset'])})
      continue
    print(
      f'{video}: {result["rows"]} transcript segments, {result["frames"]} representative frames, '
      f'{result["slides"]} extracted slides'
    )
    if result['transcript_error']:
      print(f'{video}: transcript incomplete: {result["transcript_error"]}')
    if result['slide_error']:
      print(f'{video}: slides incomplete: {result["slide_error"]}')
  return 1 if failures else 0


def _utf8_output():
  """Help, paths and summaries contain Chinese. Pipes get UTF-8 (the GUI and other programs read that); a console
  keeps its encoding but shows a replacement character instead of crashing on what it cannot encode."""
  for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, 'reconfigure'):
      stream.reconfigure(errors='replace', **({} if stream.isatty() else {'encoding': 'utf-8'}))


def main(argv=None):
  _utf8_output()
  argv = sys.argv[1:] if argv is None else argv
  if argv[:1] == ['_yt-dlp']:  # internal: the bundled yt-dlp, for frozen builds (see download.executable)
    import yt_dlp

    return yt_dlp.main(argv[1:])
  parser = build_parser()
  args = parser.parse_args(argv)
  try:
    return run(args)
  except KeyboardInterrupt:
    return 130
  except (OSError, MediaError, RuntimeError, ValueError) as error:
    parser.exit(2, f'{parser.prog}: error: {error}\n')
