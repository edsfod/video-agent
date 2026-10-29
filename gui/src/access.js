// Which CLI commands the page may run itself through cli:json and cli:text. Free of Electron, so the rule can be
// tested on its own (test/access.test.js).

// The commands the page runs and reads at once. Downloads, processing, compressing and summaries with a model go
// through the task queue, whose command lines the main process builds.
const PAGE_COMMANDS = ['show', 'fix', 'versions', 'collection', 'config', 'template', 'tools', 'pack'];

function pageCommand(args) {
  if (!Array.isArray(args) || !args.length || !args.every((arg) => typeof arg === 'string')) return false;
  if (args[0] === 'compress') return args.includes('--check');
  if (args[0] === 'summarize') return args.includes('--import');
  if (args[0] === 'collection') return args[1] !== 'update';
  return PAGE_COMMANDS.includes(args[0]);
}

module.exports = { pageCommand };
