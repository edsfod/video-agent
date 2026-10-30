// The JSON the video-agent CLI prints with --json, and its manifest.json and collection.json.
// Written by scripts/cli_types.py from src/video_agent/contract.py; change that file, not this one.

export type JsonVersion = 1;
export type CollectionVersion = 1;

export type CompressionState = 'compressed' | 'efficient' | 'not-smaller' | null;

/** `tools --json`: where each program comes from, None when missing, and the version of this contract. */
export interface Tools {
  json_version: number;
  ffmpeg: string | null;
  ffprobe: string | null;
  yt_dlp: string | null;
  slide_extractor: string | null;
}

/** `config --json`. */
export interface Config {
  provider: string;
  model: string | null;
  base_url: string;
  key: string | null;
  settings: string;
}

export interface Stream {
  index: number | null;
  type: string | null;
  codec: string | null;
  language: string | null;
}

export interface TranscriptEntry {
  source: string;
  segments: number;
  error: string | null;
  srt: string | null;
  clean?: string | null;
  corrections?: number;
}

export interface Picture {
  time_s: number;
  path: string;
}

export interface PointedFrame {
  time_s: number;
  path: string;
  text: string;
}

export interface Layout {
  kind: 'screen' | 'split' | 'inset' | 'projected' | 'camera';
  size: number[];
  screen: number[] | null;
  camera: number[] | null;
  activity: number[];
  picture: string | null;
  given: boolean;
  warning: string | null;
}

export interface Options {
  frame_interval: number;
  scene_threshold: number;
  max_frames: number | null;
}

export interface Limits {
  frames: number;
  frames_found: number;
  pages: number;
  pages_found: number;
  page_shown_at_least_s: number;
}

export interface SlideExtraction {
  enabled: boolean;
  imported?: string | null;
  output: string | null;
  timeline: string | null;
  error: string | null;
  slides: Picture[];
}

export interface Manifest {
  schema_version: number;
  source_video: string;
  updated_utc: string;
  duration_s: number;
  streams: Stream[];
  transcript: TranscriptEntry;
  representative_frame_run: string;
  layout?: Layout;
  pointed_frames?: PointedFrame[];
  options?: Options;
  screen_pages?: Picture[];
  limits?: Limits;
  representative_frames: Picture[];
  slide_extraction: SlideExtraction;
  summary_context: string;
  summary_generated: boolean;
}

/** `show`: a video's processing folder, without changing anything. */
export interface Show {
  video: string;
  duration_s: number;
  folder: string;
  processed: boolean;
  manifest: Manifest | null;
  summary: string | null;
  context: string | null;
  transcript: string | null;
  transcript_original: string | null;
  corrections: string[][];
  extra_frames: string[];
  subtitles: string | null;
  compression: CompressionState;
}

/** `process --json`, one line per video that was processed. */
export interface Processed {
  video: string;
  asset: string;
  rows: number;
  frames: number;
  slides: number;
  transcript_error: string | null;
  slide_error: string | null;
  source: string;
  reused?: boolean;
}

/** A line for a video that failed, from `process --json` and `compress --json`. */
export interface Failed {
  video: string;
  error: string;
}

/** `download --json` and `collection update --json`, one line per saved file; `new` is false for a file that was
 * there already.
 */
export interface Saved {
  path: string;
  new: boolean;
}

export interface Playlist {
  url: string;
  title: string;
  count: number;
  titles: string[];
}

/** `download --json` for a link that stands for a list, downloaded only with --playlist. */
export interface PlaylistFound {
  playlist: Playlist;
}

export interface Change {
  time: string;
  before: string;
  after: string;
}

/** `fix --json`. */
export interface Fixed {
  corrections: string[][];
  unmatched: string[];
  changed_lines: number;
  changes: Change[];
}

/** `compress --check --json`, one line per video. */
export interface Checked {
  video: string;
  state: CompressionState;
}

/** `compress --json`, one line per video; `skipped` says why it was left as it was. */
export interface Compressed {
  video: string;
  skipped: string | null;
  before: number;
  after: number;
  still: boolean | null;
}

export interface Version {
  file: string;
  created: string;
  source: string;
  note: string;
  path: string;
  pictures: string | null;
}

/** `versions --json`: the current text and the others, newest first. */
export interface Versions {
  current: Version | null;
  versions: Version[];
}

export interface PictureNode {
  id: string;
  parent: string | null;
  created: string;
  source: string;
  note: string;
  members: string[];
  dropped: string[];
}

/** `pictures --json`: the sets of a video's pictures, the root (every picture) first, and the one in use. */
export interface Pictures {
  current: string;
  nodes: PictureNode[];
}

/** `template --list` (a list of these), and `template NAME --info|--use|--edit|--accept|--reset|--copy NEW`. */
export interface Template {
  name: string;
  path: string;
  builtin: boolean;
  customized: boolean;
  outdated: boolean;
  default: string | null;
  current: boolean;
}

/** `template NAME --reset` for a template of the user's own. */
export interface TemplateDeleted {
  name: string;
  deleted: boolean;
}

/** The list a collection follows. */
export interface Source {
  url: string;
  folder: string;
  auto: boolean;
  checked: string | null;
  new: number;
}

/** collection.json. Files written before 1.1.0 have no schema_version. */
export interface CollectionData {
  schema_version?: number;
  name: string;
  videos: string[];
  terms: string[][];
  skipped: Record<string, string>;
  source?: Source | null;
}

export interface Member {
  index: number;
  video: string;
  name: string;
  folder: string;
  processed: boolean;
  summary: string | null;
  duration_s: number | null;
  speech_share: number | null;
  maybe_empty: boolean;
  skipped: string | null;
  compression: CompressionState;
}

/** `collection NAME <action>` and `collection list` (a list of these). */
export interface Collection {
  name: string;
  folder: string;
  overview: string | null;
  guide: string | null;
  overview_behind: number[];
  guide_behind: number[];
  terms: string[][];
  source: Source | null;
  videos: Member[];
}

/** `inspect`: ffprobe's streams as they come. */
export interface Inspected {
  path: string;
  duration_s: number;
  streams: Record<string, unknown>[];
}

/** What each command prints; a command that prints several lines gives the type of one line. */
export interface CliOutputs {
  tools: Tools;
  config: Config;
  show: Show;
  inspect: Inspected;
  process: Processed | Failed;
  download: Saved | PlaylistFound;
  fix: Fixed;
  compress: Compressed | Checked | Failed;
  versions: Versions;
  pictures: Pictures;
  template: Template | TemplateDeleted | Template[];
  collection: Collection | Collection[] | Saved;
  models: string[];
}
