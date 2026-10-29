// The model lists read from what each agent prints or keeps (models.js), without a window.

const test = require('node:test');
const assert = require('node:assert/strict');
const { piModels, dshModels, effortArgs } = require('../src/models');

test('pi --list-models gives provider/model values', () => {
  const text = [
    'provider  model          context  max-out  thinking  images',
    'openai    gpt-4.1        1.0M     32.8K    no        yes',
    'anthropic claude-sonnet  200K     64K      yes       yes',
    '',
  ].join('\n');
  assert.deepEqual(piModels(text).map((model) => model.value), ['openai/gpt-4.1', 'anthropic/claude-sonnet']);
});

test('DeepSeek Harness lists the models its config names, the one in use first', () => {
  const dump = [
    '- id: agent-default-model',
    "  name: '@deepseek-ai/dsh-agent-default-model'",
    '  config:',
    '    provider: deepseek-official',
    '    model: deepseek-flash',
    '- id: llm-deepseek',
    '  config:',
    '    models:',
    '      - id: deepseek-flash',
    '        name: DeepSeek-V4.1-Flash',
    '      - id: deepseek-pro',
    '',
  ].join('\n');
  const found = dshModels(dump);
  assert.deepEqual(found.map((model) => model.value).slice(0, 2), ['deepseek-flash', 'deepseek-pro']);
  assert.match(found[0].label, /现在用的/);
});

test('each agent gets the thinking level its own way, and nothing when none is chosen', () => {
  assert.deepEqual(effortArgs('claude', 'high'), ['--effort', 'high']);
  assert.deepEqual(effortArgs('codex', 'low'), ['-c', 'model_reasoning_effort="low"']);
  assert.deepEqual(effortArgs('pi', 'max'), ['--thinking', 'max']);
  assert.deepEqual(effortArgs('hermes', 'ultra'), ['--reasoning', 'ultra']);
  assert.deepEqual(effortArgs('dsh', 'high'), []);
  assert.deepEqual(effortArgs('claude', ''), []);
});
