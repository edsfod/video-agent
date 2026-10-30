# Working rules

Rules for all work on this project, and nothing else. A rule for one part lives in that part's document; why a rule exists, and when it was decided, is in `decisions/` and the git history. Nothing loads this file on its own: there is no `AGENTS.md` or `CLAUDE.md` for now, and no rule lives in Claude's memory, so a session reads it when told to.

## Where things go

| What | Where |
| --- | --- |
| How to work on it | this file |
| What the product is and is not | `docs/product-rules.md` |
| Why it is built as it is; decisions by topic, those Claude made marked `Claude judgment` | `docs/decisions/` |
| The code as it is now | `ARCHITECTURE.md` |
| Commands and options | `docs/commands.md` |
| Each release's notes, and the checks it passed | `docs/releases/`, `docs/release-log.md` |
| Research (not published) | `notes/` |

Keep a change's documents in the same commit as the change.

## Working

- Reply to the user in Chinese. Repository text stays in the language it is written in.
- Fix what is clearly wrong and report it. Ask only about product decisions, and about steps that go outward or cannot be undone.
- Add no allow-list, restriction or defensive limit nobody asked for; ask first.
- Do not change the user's Clash proxy rules.
- Push straight to `main`: `git pull --rebase` after committing, then push. `.git/hooks/pre-push` runs the tests the change touches; do not wait for GitHub's runs, and fix what they find next.
- Tests run on this machine with their windows off the screen (`VA_E2E_BACKGROUND=1`), never touching the user's real settings; they wait on state, not on timing. When wording changes, search the tests for the old text. Installer tests (install, PATH, update) run only on GitHub, for packaging changes.
- Python that writes text passes `newline='\n'`; `.gitattributes` keeps the repository in LF.
- Every long run has a time limit and writes its output straight to a file that is read while it runs, never through `grep` or `tail`, and never left to a completion notice: a hung process sends none.
- End processes by PID, never by image name. In `gh` monitors use `gh --jq`, never a standalone `jq`.
- Find out what a web page holds by script (its DOM, data and requests), never from a screenshot, and filter what the script prints: requests and responses carry sign-in tokens.

## Releasing

- Release only when the user says, and do not suggest it.
- Set the version with `uv run scripts/bump_version.py <version>`, write `docs/releases/v<version>.md` by hand, tag and push; GitHub builds it.
- From the user's word on, nothing waits for review: when the checks pass (signed `latest.yml` and its size, FFmpeg source digests, packaged tests), publish the draft, check the three update sources and record it in `docs/release-log.md`. Stop only if a check fails.

## Writing

- Rules are written as rules: no dates, history or reasons in this file or in `product-rules.md`.
- Commit messages say what changed and carry no AI attribution trailer.
- Text for people is plain, direct Chinese with no stock thanks or translated sentence shapes, its claims at the strength of the evidence. Text sent to others under the user's name is shown to them first; release notes are not, and include the code changes.
- Examples in prompts for a model are placeholders, never real video content: a model takes them for the video's own.
- Code reads like the code around it: its comment density, naming and idiom.
