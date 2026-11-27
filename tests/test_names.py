"""The file and folder names the desktop app and the skill rely on are the ones the CLI writes (ARCHITECTURE.md, A7).
Renaming one on either side without the other fails here."""

from pathlib import Path

from video_agent import cli, collection, evidence, removal

ROOT = Path(__file__).resolve().parents[1]

# The draft is saved beside the summary under the summary's name (importer.draft_path).
DRAFT = f'{Path(evidence.SUMMARY_NAME).stem}.draft.md'

# Each name, and the files outside the CLI that spell it out.
USED = {
  evidence.SUMMARY_NAME: ['gui/src/chat-rounds.js', 'gui/src/jobs.js', 'gui/src/renderer/summary.js'],
  DRAFT: ['gui/src/jobs.js'],
  collection.OVERVIEW: ['gui/src/jobs.js'],
  collection.GUIDE: ['gui/src/jobs.js'],
  cli.DOWNLOADS: ['gui/src/jobs.js', 'gui/src/renderer/video-view.js'],
}
SKILL = [evidence.SUMMARY_NAME, DRAFT]


def test_the_app_spells_the_names_the_cli_writes():
  for name, files in USED.items():
    for file in files:
      assert f"'{name}'" in (ROOT / file).read_text(encoding='utf-8'), f'{file} does not use {name}'


def test_the_skill_names_the_files_the_cli_writes():
  skill = (ROOT / 'skills' / 'video-agent' / 'SKILL.md').read_text(encoding='utf-8')
  for name in SKILL:
    assert f'`{name}`' in skill, f'SKILL.md does not name {name}'


def test_deleting_looks_in_the_folder_downloads_go_to():
  assert removal.DOWNLOADS == cli.DOWNLOADS
