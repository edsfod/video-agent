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
      tests/*) why='CLI tests: cli'; cli=true ;;
      gui/test/installer-path.test.js | gui/test/update-install.test.js)
        why='installer: installer'; installer=true ;;
      gui/*) why='window: gui, installer'; gui=true installer=true ;;
      packaging/* | .github/actions/ffmpeg/*) why='packaging: installer'; installer=true ;;
      .github/workflows/release.yml | .github/workflows/ffmpeg.yml) why='release only: none' ;;
      docs/* | notes/* | LICENSE | *.md) why='documentation: none' ;;
      *) why='unknown: all'; cli=true gui=true installer=true ;;
    esac
    echo "  $file ($why)"
  done < <(git diff --name-only "$base" HEAD)
fi

echo "jobs: cli=$cli gui=$gui installer=$installer"
out=${GITHUB_OUTPUT:-/dev/stdout}
printf 'cli=%s\ngui=%s\ninstaller=%s\n' "$cli" "$gui" "$installer" >> "$out"
