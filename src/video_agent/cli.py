"""Command-line interface for local video evidence preparation and optional downloads."""

import argparse
import getpass
import json
import sys
from pathlib import Path

from . import settings
from .download import DownloadError, download_urls
from .media import MediaError, duration, parse_clock, probe, save_frame
from .processor import asset_folder, process_video
from .summarize import import_summary, material, pack, summarize_video, template


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
    '--max-frames', type=positive_int, default=36, help='maximum representative frames per video (default: 36)'
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
  summarize.add_argument('video', type=Path)
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
    '--max-images', type=positive_int, default=40, help='frames sent with the first request (default: 40)'
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
  packing.add_argument('video', type=Path)
  packing.add_argument(
    '-o',
    '--output',
    type=Path,
    default=Path.cwd() / 'video-agent-output',
    help='the workspace passed to process (default: video-agent-output)',
  )
  packing.add_argument('--request', default='', help="the user's wishes for this summary")
  packing.add_argument('--zip', type=Path, help='write 提示词.md and the frames into this zip file')
  packing.add_argument('--max-images', type=positive_int, default=40, help='frames put into the zip (default: 40)')

  config = commands.add_parser('config', help='show or change the summarize provider, model, base URL and API key')
  config.add_argument('--provider', choices=tuple(settings.PROVIDERS), help='choose the provider to use and edit')
  config.add_argument('--model')
  config.add_argument('--base-url')
  keys = config.add_mutually_exclusive_group()
  keys.add_argument('--set-key', action='store_true', help='read an API key and save it in Windows Credential Manager')
  keys.add_argument('--delete-key', action='store_true', help='remove the saved API key')
  config.add_argument('--json', action='store_true', help='print the resulting settings as JSON')

  show = commands.add_parser('show', help="print JSON about a video's processing folder without changing anything")
  show.add_argument('video', type=Path)
  show.add_argument(
    '-o',
    '--output',
    type=Path,
    default=Path.cwd() / 'video-agent-output',
    help='the workspace passed to process (default: video-agent-output)',
  )

  commands.add_parser('template', help='print the summary rules and template shared by the skill and summarize')
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
      'transcript': existing('transcript.txt'),
      'extra_frames': sorted(str(path) for path in (asset / 'frames' / 'extra').glob('frame-*.jpg')),
    }
  )
  return 0


def run(args):
  if args.command == 'download':
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
      )
    except DownloadError as error:
      print(f'download: ERROR: {error}')
      return 1
    for path in paths:
      if args.json:
        _emit({'path': str(path)})
      else:
        print(f'Next: process this local file separately: {path}')
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

  if args.command == 'show':
    return _show(args)

  if args.command == 'template':
    sys.stdout.write(template())
    return 0

  if args.command == 'config':
    return _config(args)

  if args.command == 'summarize' and args.import_from:
    # Bytes, not text: the GUI sends UTF-8, whatever code page a frozen build would decode stdin with.
    source = sys.stdin.buffer.read() if args.import_from == '-' else Path(args.import_from).read_bytes()
    text = source.decode('utf-8-sig')
    print(import_summary(args.video, args.output, text, overwrite=args.overwrite))
    return 0

  if args.command == 'pack':
    if args.zip:
      target, count = pack(args.video, args.output, args.zip, request=args.request, max_images=args.max_images)
      print(f'{target} ({count} frames)')
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
