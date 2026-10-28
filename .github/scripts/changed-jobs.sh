#!/usr/bin/env bash
# Which test.yml jobs a push needs, from the files it changed. Prints cli=, gui= and installer= (true/false) to
# $GITHUB_OUTPUT, or to stdout when run by hand: bash .github/scripts/changed-jobs.sh [base].
#
# The jobs follow how the parts depend on each other: the window drives the real CLI (it must not duplicate its
# logic), and the installer bundles the CLI, the window and the skill. So the CLI's code runs every job, the window's
# code runs gui and installer, packaging runs installer, and documentation runs none. A file no rule knows runs every
# job, so a missing rule costs time, never a test.
#
# The base is what the branch adds to main (all its commits, also those of runs a later push cancelled), what a push
# to main added, or a pull request's base. Without a base every job runs.
#
# A push to main is a fast-forward to a commit that already passed on its branch, so main repeats nothing, except to
# fill the caches that later branches read (a branch reads only main's caches and its own): the npm and Electron
# downloads when gui/package-lock.json changed, the LGPL FFmpeg when its build script changed.
set -euo pipefail

base=${1:-}
if [ -z "$base" ]; then
  case "${EVENT:-}" in
    pull_request) base=${PR_BASE:-} ;;
    push)
      if [ "${REF:-}" = main ]; then
        base=${BEFORE:-}
      else
        base=$(git merge-base HEAD origin/main 2>/dev/null || true)
      fi
      ;;
  esac
fi
case "$base" in '' | 0000000000000000000000000000000000000000) base= ;; esac
if [ -n "$base" ] && ! git cat-file -e "$base^{commit}" 2>/dev/null; then base=; fi

cli=false gui=false installer=false
if [ -z "$base" ]; then
  echo "no base to compare with: every job runs"
  cli=true gui=true installer=true
else
  echo "files changed since $(git rev-parse --short "$base"):"
  while IFS= read -r file; do
    [ -n "$file" ] || continue
    case "$file" in
      src/* | pyproject.toml | uv.lock | skills/* | .claude-plugin/* | .agents/* | plugin.json)
        why='CLI or skill: all'; cli=true gui=true installer=true ;;
      tests/* | scripts/*) why='CLI tests or maintenance scripts: cli'; cli=true ;;
      gui/test/installer-path.test.js | gui/test/update-install.test.js)
        why='installer: installer'; installer=true ;;
      gui/*) why='window: gui, installer'; gui=true installer=true ;;
      packaging/* | .github/actions/ffmpeg/*) why='packaging: installer'; installer=true ;;
      .github/workflows/release.yml) why='release only: none' ;;
      docs/* | notes/* | LICENSE | *.md) why='documentation: none' ;;
      *) why='unknown: all'; cli=true gui=true installer=true ;;
    esac
    echo "  $file ($why)"
  done < <(git diff --name-only "$base" HEAD)
fi

if [ -n "$base" ] && [ "${EVENT:-}" = push ] && [ "${REF:-}" = main ] && [ -n "${SHA:-}" ]; then
  tested=$(gh api "repos/$REPO/actions/runs?head_sha=$SHA&status=success&per_page=30" \
    --jq '[.workflow_runs[] | select(.name == "test" and .head_branch != "main")] | length' 2>/dev/null || echo 0)
  if [ "$tested" -gt 0 ]; then
    echo "${SHA:0:7} already passed on its branch: main only fills caches that changed"
    changed=$(git diff --name-only "$base" HEAD)
    cli=false gui=false installer=false
    if grep -qx 'gui/package-lock.json' <<<"$changed"; then gui=true installer=true; fi
    if grep -qx 'packaging/ffmpeg/build.sh' <<<"$changed"; then installer=true; fi
  fi
fi

echo "jobs: cli=$cli gui=$gui installer=$installer"
out=${GITHUB_OUTPUT:-/dev/stdout}
printf 'cli=%s\ngui=%s\ninstaller=%s\n' "$cli" "$gui" "$installer" >> "$out"
