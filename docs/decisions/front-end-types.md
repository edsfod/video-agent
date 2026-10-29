# Front-end types — user decision (2026-10-29), on Claude's proposal

An outside review of 0.9.2-beta found the desktop app the weakest part: `app.js` one file of about 2,000 lines (2,219 at 1.0.0) with one global `state` and some 80 top-level functions, `main.js` doing IPC, Agent command lines, plugin installs, tray and windows, no types, and the JSON between the app and the CLI defined nowhere but in the code on each side (`manifest.json` has `schema_version: 1`; `collection.json` and the `--json` output have none). The user asked whether to move from JavaScript to TypeScript.

Not now (Claude's proposal, which the user accepted):

- Renaming to `.ts` does not split `app.js`; it would still be one file of 2,000 lines, with types.
- The contract that most needs types runs between Python and JavaScript. Types written on the JavaScript side alone would not notice the CLI changing a field.
- The window has no build step: `index.html` loads `app.js` and the libraries straight from `node_modules`, the tests run the sources, and electron-builder packs them as they are. TypeScript would add a compile step to packaging, the end-to-end tests and `test:dist`.
- Type checking is what helps, especially as Agents write most of the code: a renamed field is reported everywhere it is used, not only where an end-to-end test happens to pass. JSDoc with `// @ts-check` and `tsc --noEmit --checkJs` gives that without changing what runs, and the types carry over if the files are renamed later.

The order:

1. **The CLI's JSON.** Types for the `--json` output on the Python side (TypedDict or dataclasses, checked with mypy or pyright), a version field in `collection.json` and the JSON output, a `.d.ts` for the app, and a test that the two agree. With it, the IPC narrows: `cli:json` and `cli:text` take only known commands, `shell:open` only paths inside the workspace.
2. **Type checking in the app.** `// @ts-check` file by file, the small modules first (`preload.js`, `tasks.js`, `main.js`), `app.js` last; `tsc` in the pre-push hook and CI.
3. **Splitting `app.js`** by view (videos and summaries, collections, settings, task queue, terminal), with the state in a module of its own. First check that `<script type="module">` from `file://` works with the page's CSP.
4. **Then decide on `.ts`**, when each file is small and the change is renaming plus a bundler.
