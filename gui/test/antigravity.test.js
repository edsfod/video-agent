// How the Antigravity route shows its agent's steps (antigravity.js); the steps as GetCascadeTrajectory gives them.
const test = require('node:test');
const assert = require('node:assert/strict');
const { stepLine } = require('../src/antigravity');

test('an Antigravity step shows as a line: what the agent says, the commands it runs, what waits for the user', () => {
  const done = 'CORTEX_STEP_STATUS_DONE';
  assert.equal(stepLine({ type: 'CORTEX_STEP_TYPE_USER_INPUT', status: done }), null);
  assert.equal(stepLine({ type: 'CORTEX_STEP_TYPE_PLANNER_RESPONSE', status: done, plannerResponse: { thinking: '想一下' } }), null);
  assert.equal(stepLine({ type: 'CORTEX_STEP_TYPE_PLANNER_RESPONSE', status: done, plannerResponse: { response: ' 已保存。 ' } }), '已保存。');
  assert.equal(stepLine({ type: 'CORTEX_STEP_TYPE_RUN_COMMAND', status: done, runCommand: { commandLine: 'video-agent template' } }), '▸ video-agent template');
  assert.equal(
    stepLine({ type: 'CORTEX_STEP_TYPE_VIEW_FILE', status: done, viewFile: { absolutePathUri: 'file:///C:/work/%E6%80%BB%E7%BB%93.md' } }),
    '▸ 读 C:/work/总结.md',
  );
  assert.equal(stepLine({ type: 'CORTEX_STEP_TYPE_GENERIC', status: done, generic: { args: { toolSummary: 'Write the draft' } } }), '▸ Write the draft');
  assert.match(stepLine({ type: 'CORTEX_STEP_TYPE_RUN_COMMAND', status: 'CORTEX_STEP_STATUS_WAITING' }), /^等你在 Antigravity 里确认/);
});
