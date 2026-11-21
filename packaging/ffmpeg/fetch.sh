#!/usr/bin/env bash
# Prepares and verifies build/ffmpeg without compiling from scratch when packaging/ffmpeg/build.sh has the pinned
# build_hash (comments and blank lines stripped; docs/design/distribution.md).
# build/ffmpeg/BUILD-HASH names the build_hash the tree was built from, so a tree from an older build.sh is not taken.
# Only whole-line comments are left out of the hash: a comment at the end of a line in build.sh counts as a change.
# Usage:
#   bash packaging/ffmpeg/fetch.sh --hash    # prints the comment-stripped sha256 of packaging/ffmpeg/build.sh
#   bash packaging/ffmpeg/fetch.sh --verify  # checks an existing build/ffmpeg tree against build.sh
#   bash packaging/ffmpeg/fetch.sh --mark    # after running build.sh: checks the new tree and writes BUILD-HASH
#   bash packaging/ffmpeg/fetch.sh           # verifies build/ffmpeg, or downloads and verifies the prebuilt archive;
#                                            # exits 2 when build.sh changed and no prebuilt archive is pinned for it
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
BUILD_SH=$ROOT/packaging/ffmpeg/build.sh
OUT=$ROOT/build/ffmpeg
MARK=$OUT/BUILD-HASH

PREBUILT_TAG=v0.9.0
PREBUILT_BUILD_HASH=debbfb3de887c67aca002a5a15b2714ed67774dd7d3dec3bed996fe674a1a877
PREBUILT_ARCHIVE_SHA256=c9b602d794eaf3097735b99409258b6510cc8c57f7a53859faf705d2054436fa

build_hash() {
  grep -v -E '^[[:space:]]*(#|$)' "$BUILD_SH" | tr -d '\r' | sha256sum | cut -d' ' -f1
}

read_var() {
  sed -n "s/^$1=//p" "$BUILD_SH" | tr -d '\r' | head -1
}

# What Video Agent needs from the build, as kind:name, read from the check at the end of build.sh so it is listed once.
required() {
  sed -n '/^for kind_name in /,/; do$/p' "$BUILD_SH" | tr -d '\r\\' | sed 's/^for kind_name in //; s/; do$//'
}

# The tree has the sources build.sh pins, the licences, an LGPL ffmpeg.exe and everything required.
verify_contents() {
  local ffmpeg_ver ffmpeg_sha dav1d_ver dav1d_sha svt_ver svt_sha bin
  ffmpeg_ver=$(read_var FFMPEG_VERSION)
  ffmpeg_sha=$(read_var FFMPEG_SHA256)
  dav1d_ver=$(read_var DAV1D_VERSION)
  dav1d_sha=$(read_var DAV1D_SHA256)
  svt_ver=$(read_var SVTAV1_VERSION)
  svt_sha=$(read_var SVTAV1_SHA256)

  bin="$OUT/bin/ffmpeg.exe"
  [ -f "$bin" ] && [ -f "$OUT/bin/ffprobe.exe" ] && [ -f "$OUT/BUILD.txt" ] || return 1
  for lic in FFmpeg-LGPL-2.1.txt FFmpeg-LICENSE.md dav1d-COPYING.txt SVT-AV1-LICENSE.md SVT-AV1-PATENTS.md zlib-LICENSE.txt; do
    [ -f "$OUT/licenses/$lic" ] || return 1
  done
  printf '%s  %s\n' \
    "$ffmpeg_sha" "$OUT/source/ffmpeg-$ffmpeg_ver.tar.xz" \
    "$dav1d_sha" "$OUT/source/dav1d-$dav1d_ver.tar.xz" \
    "$svt_sha" "$OUT/source/SVT-AV1-v$svt_ver.tar.gz" | sha256sum -c - >/dev/null 2>&1 || return 1

  "$bin" -hide_banner -L | grep -q 'GNU Lesser General Public' || return 1
  local wanted kind_name
  wanted=$(required)
  [ -n "$wanted" ] || { echo "build.sh 里找不到所需组件的清单（for kind_name in …）" >&2; return 1; }
  for kind_name in $wanted; do
    # The name is the second column of -filters, -decoders and -encoders; a word in a description does not count.
    "$bin" -hide_banner -"${kind_name%%:*}" | awk -v name="${kind_name#*:}" '$2 == name { found = 1 } END { exit !found }' ||
      return 1
  done
}

# As verify_contents, and built from the build.sh there is now.
verify_tree() {
  [ -f "$MARK" ] && [ "$(tr -d '\r\n' <"$MARK")" = "$(build_hash)" ] || return 1
  verify_contents
}

case "${1:-}" in
  --hash)
    build_hash
    exit 0
    ;;
  --verify)
    verify_tree
    exit 0
    ;;
  --mark)
    verify_contents || { echo "build/ffmpeg 未通过校验，不写 BUILD-HASH" >&2; exit 1; }
    build_hash >"$MARK"
    exit 0
    ;;
esac

if verify_tree; then
  echo "build/ffmpeg 已就绪并校验通过"
  exit 0
fi

hash=$(build_hash)
if [ "$hash" != "$PREBUILT_BUILD_HASH" ]; then
  echo "build.sh 的有效内容哈希 ($hash) 与预编译包 ($PREBUILT_BUILD_HASH) 不同，需要重新编译" >&2
  exit 2
fi

name="ffmpeg-lgpl-$hash.tar.gz"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
url="https://github.com/edsfod/video-agent/releases/download/$PREBUILT_TAG/$name"
if command -v gh >/dev/null 2>&1 && gh release download "$PREBUILT_TAG" -R edsfod/video-agent -p "$name" -D "$tmp" 2>/dev/null; then
  :
else
  curl -sSfL --retry 3 "$url" -o "$tmp/$name"
fi
echo "$PREBUILT_ARCHIVE_SHA256  $tmp/$name" | sha256sum -c -
rm -rf "$OUT"
mkdir -p "$OUT"
tar -xzf "$tmp/$name" -C "$OUT"
echo "$hash" >"$MARK"
verify_tree || { echo "预编译包解压后未通过校验" >&2; exit 1; }
echo "已下载并校验预编译的 build/ffmpeg ($name)"
