# Front-end types — user decision (2026-10-29), on Claude's proposal

An outside review of 0.9.2-beta found the desktop app the weakest part: `app.js` one file of about 2,000 lines (2,219 at 1.0.0) with one global `state` and some 80 top-level functions, `main.js` doing IPC, Agent command lines, plugin installs, tray and windows, no types, and the JSON between the app and the CLI defined nowhere but in the code on each side (`manifest.json` has `schema_version: 1`; `collection.json` and the `--json` output have none). The user asked whether to move from JavaScript to TypeScript.

Not now (Claude's proposal, which the user accepted):

- Renaming to `.ts` does not split `app.js`; it would still be one file of 2,000 lines, with types.
- The contract that most needs types runs between Python and JavaScript. Types written on the JavaScript side alone would not notice the CLI changing a field.
- The window has no build step: `index.html` loads `app.js` and the libraries straight from `node_modules`, the tests run the sources, and electron-builder packs them as they are. TypeScript would add a compile step to packaging, the end-to-end tests and `test:dist`.
- Type checking is what helps, especially as Agents write most of the code: a renamed field is reported everywhere it is used, not only where an end-to-end test happens to pass. JSDoc with `// @ts-check` and `tsc --noEmit --checkJs` gives that without changing what runs, and the types carry over if the files are renamed later.

The order:

1. **The CLI's JSON.** Types for the `--json` output on the Python side (TypedDict or dataclasses, checked with mypy or pyright), a version field in `collection.json` and the JSON output, a `.d.ts` for the app, and a test that the two agree.
2. **Type checking in the app.** `// @ts-check` file by file, the small modules first (`preload.js`, `tasks.js`, `main.js`), `app.js` last; `tsc` in the pre-push hook and CI.
3. **Splitting `app.js`** by view (videos and summaries, collections, settings, task queue, terminal), with the state in a module of its own. First check that `<script type="module">` from `file://` works with the page's CSP.
4. **Then decide on `.ts`**, when each file is small and the change is renaming plus a bundler.

## Step 1, done (2026-10-29, for the release after 1.0.0)

- `src/video_agent/contract.py` holds a TypedDict for every JSON value the CLI prints, for `manifest.json` and for `collection.json`. Fields of the manifest added after 0.1.0 are optional, since a video processed by an older version lacks them until processed again.
- Three checks. mypy (`uv run mypy`, in the pre-push hook and CI) checks the functions that build the values; it checks only annotated functions, so the builders were annotated, and checking every function body was left out (29 findings, mostly about inferred types, Claude judgment). Every test checks each value the CLI prints against its type (`contract.CHECK`, on in `tests/conftest.py`), with no field missing or extra, so a field added in the code and not in the contract fails a test. `scripts/cli_types.py` writes `gui/src/cli-types.d.ts`, and a test fails while it is out of date.
- Versions: `tools --json` gives `json_version`, which goes up only when a field is removed or changes meaning; the window compares it with its `CLI_JSON_VERSION` (a test keeps the two equal) and, for a CLI set in the settings that differs, says so above the collections. `collection.json` carries `schema_version`; a file without one is version 1, and a newer one is refused with a message rather than misread. Claude judgment: one version for all output, read once at start, rather than a field in every line, which would have changed the shape of every result.
- **No allow-lists between the page and the main process** (user decision, 2026-10-29). A list of the CLI commands the page may run and a limit on the paths `shell:open` opens were added with this step and taken out the same day. The app is for users who also have the CLI and an embedded terminal, so such limits protect nothing they could not do anyway, and every new feature would have to be added to them.

## Step 2, done (2026-10-29)

- TypeScript 6 (a dev dependency) checks the JavaScript as it is, through JSDoc, and compiles nothing: `npm run typecheck` runs `tsc` on the main process (`gui/tsconfig.json`) and on the page (`gui/src/renderer/tsconfig.json`, with the DOM and the libraries `index.html` loads), in the pre-push hook and in CI's gui job before the tests.
- Strict mode, with two parts left off (Claude judgment): untyped parameters are allowed, since requiring a type on each would have meant some 350 annotations before the check found anything, and a caught error is `any`, as it was. The page is also not checked for null: about 80 places rely on the page's order (a button shows only when a video is open), which step 3 can type when it splits `app.js`.
- `gui/src/va.d.ts` types `window.va`: `preload.js` is checked against it, and the page sees each answer's type, read from the module that gives it where it can be (accounts, tasks, updater, logs, models). `cliJson` takes its result's type from the command named first, from `cli-types.d.ts`; `failed(result)` in `app.js` tells a CLI failure from a result.
- What the check found. One bug: downloading a list from the list dialog went on to clear the link box through a name that did not exist (`added`), so that line threw and the link stayed. The rest were typing only: electron-updater's private parts, which `updater.js` and `update-plan.js` use on purpose, are marked `any` with the reason; the element lookups `$` and `$$` give `any`, since an id or selector stands for a known kind of element that the checker cannot see.

## Step 3, done (2026-10-29)

- `app.js` (2,280 lines) is split by its sections into ES modules of 40 to 380 lines, loaded with `<script type="module">` from `file://` under the page's CSP as it was, also from `app.asar` in a packaged build (checked with the packaged end-to-end tests on an unpacked build). The code moved as it was: a script built on TypeScript's parser put each top-level statement in its module and wrote the imports and exports, and two variables that another module changed were changed through their own module instead (`openImport(target)`, the terminal counter). `failed()` and a `markdown()` helper (sanitized Markdown) sit in `state.js`; the end-to-end tests reach `loadCollections` through `window.vaPage`.
- The page is now checked for null too: `pageVideo()` and `pageCollection()` give the open video or collection for the buttons on its page, which can be clicked only while it is shown, and the other places check.
- With it, two user requests (2026-10-29): clicking the open video or collection in the sidebar again goes back to the start page (a collection's row, while one of its videos is open, still opens the collection's page), and the 终端 tab no longer starts a shell when opened; its button reads 启动终端 until one runs, then 新建终端, and choosing another shell replaces only a running one.

## Step 4: staying with JavaScript (user decision, 2026-10-29)

The app is not moved to `.ts`. Every file is small and `tsc` already checks all of it through JSDoc, null included; `.ts` would add a compile step to packaging and the tests for a shorter way of writing the same types.

