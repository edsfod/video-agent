"""The JSON contract between the CLI and the desktop app (contract.py): outputs the other tests do not reach, the
check itself, the version of collection.json, and the app's TypeScript copy of the types."""

import importlib.util
import json
from pathlib import Path

import pytest

from video_agent import cli, collection, contract

ROOT = Path(__file__).resolve().parents[1]


def _json(capsys):
  return json.loads(capsys.readouterr().out)


def test_collection_fix_inspect_and_a_deleted_template_print_their_types(sample_video, tmp_path, capsys):
  workspace = tmp_path / 'work'
  assert cli.main(['process', str(sample_video), '-o', str(workspace), '--json']) == 0
  capsys.readouterr()
  assert cli.main(['collection', 'create', '课', str(sample_video), '-o', str(workspace)]) == 0
  made = _json(capsys)
  assert made['videos'][0]['processed'] and made['videos'][0]['duration_s'] > 7
  assert cli.main(['collection', 'skip', '课', str(sample_video), '--reason', '空', '-o', str(workspace)]) == 0
  assert _json(capsys)['videos'][0]['skipped'] == '空'
  assert cli.main(['collection', 'terms', '课', '--replace', '图表', '图标', '-o', str(workspace)]) == 0
  assert _json(capsys)['terms'] == [['图表', '图标']]
  assert cli.main(['collection', 'list', '-o', str(workspace)]) == 0
  assert [entry['name'] for entry in _json(capsys)] == ['课']

  assert cli.main(['fix', str(sample_video), '-o', str(workspace), '--replace', '测试', '试验', '--json']) == 0
  fixed = _json(capsys)
  assert fixed['unmatched'] == [] and fixed['changed_lines'] == 2  # the collection's term changed the other line
  assert cli.main(['inspect', str(sample_video)]) == 0
  assert _json(capsys)['streams']

  assert cli.main(['template', '标准', '--copy', '我的']) == 0
  assert _json(capsys)['name'] == '我的'
  assert cli.main(['template', '我的', '--reset']) == 0
  assert _json(capsys) == {'name': '我的', 'deleted': True}


def test_the_check_finds_missing_extra_and_wrong_fields():
  good = {'video': 'a.mp4', 'error': 'no'}
  contract.check(good, contract.Failed)
  for bad in ({'video': 'a.mp4'}, {**good, 'more': 1}, {**good, 'error': 3}):
    with pytest.raises(contract.ContractError):
      contract.check(bad, contract.Failed)
  contract.check({'path': 'a', 'new': False}, contract.Saved | contract.PlaylistFound)
  with pytest.raises(contract.ContractError):
    contract.check({'time_s': True, 'path': 'a'}, contract.Picture)  # a bool is not a number


def test_collection_json_carries_its_version_and_a_newer_one_is_refused(tmp_path):
  collection.create(tmp_path, '课')
  path = collection.folder(tmp_path, '课') / collection.DATA
  data = json.loads(path.read_text(encoding='utf-8'))
  assert data['schema_version'] == contract.COLLECTION_VERSION
  contract.check(data, contract.CollectionData)

  del data['schema_version']  # as written before 1.1.0
  path.write_text(json.dumps(data), encoding='utf-8')
  assert collection.load(tmp_path, '课')['name'] == '课'
  path.write_text(json.dumps({**data, 'schema_version': contract.COLLECTION_VERSION + 1}), encoding='utf-8')
  with pytest.raises(collection.CollectionError, match='newer'):
    collection.load(tmp_path, '课')


def test_the_apps_types_are_written_from_the_contract():
  spec = importlib.util.spec_from_file_location('cli_types', ROOT / 'scripts' / 'cli_types.py')
  script = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(script)
  written = (ROOT / 'gui' / 'src' / 'cli-types.d.ts').read_text(encoding='utf-8')
  assert written == script.render(), 'gui/src/cli-types.d.ts is out of date: run uv run scripts/cli_types.py'


def test_the_window_reads_the_json_version_the_cli_prints():
  app = (ROOT / 'gui' / 'src' / 'renderer' / 'state.js').read_text(encoding='utf-8')
  assert f'const CLI_JSON_VERSION = {contract.JSON_VERSION};' in app
