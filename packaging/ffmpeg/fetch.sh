#!/usr/bin/env bash
# Prepares and verifies build/ffmpeg without compiling from scratch when packaging/ffmpeg/build.sh has the pinned
# build_hash (comments and blank lines stripped; docs/design/distribution.md).
# Usage:
#   bash packaging/ffmpeg/fetch.sh --hash    # prints the comment-stripped sha256 of packaging/ffmpeg/build.sh
#   bash packaging/ffmpeg/fetch.sh --verify  # checks an existing build/ffmpeg tree against build.sh
#   bash packaging/ffmpeg/fetch.sh           # verifies build/ffmpeg, or downloads and verifies the prebuilt archive
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
BUILD_SH=$ROOT/packaging/ffmpeg/build.sh
OUT=$ROOT/build/ffmpeg

PREBUILT_TAG=v0.9.0
PREBUILT_BUILD_HASH=debbfb3de887c67aca002a5a15b2714ed67774dd7d3dec3bed996fe674a1a877
PREBUILT_ARCHIVE_SHA256=c9b602d794eaf3097735b99409258b6510cc8c57f7a53859faf705d2054436fa

build_hash() {
  grep -v -E '^[[:space:]]*(#|$)' "$BUILD_SH" | tr -d '\r' | sha256sum | cut -d' ' -f1
}

read_var() {
  sed -n "s/^$1=//p" "$BUILD_SH" | tr -d '\r' | head -1
}

verify_tree() {
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
  for kind_name in filters:freezedetect filters:tblend filters:drawbox filters:tile filters:select decoders:libdav1d \
    decoders:hevc decoders:h264 encoders:mjpeg encoders:aac encoders:mpeg4 encoders:srt encoders:libsvtav1; do
    "$bin" -hide_banner -"${kind_name%%:*}" | grep -qw "${kind_name#*:}" || return 1
  done
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
esac

if verify_tree; then
  echo "build/ffmpeg 已就绪并校验通过"
  exit 0
fi

hash=$(build_hash)
if [ "$hash" != "$PREBUILT_BUILD_HASH" ]; then
  echo "build.sh 的有效内容哈希 ($hash) 与预编译包 ($PREBUILT_BUILD_HASH) 不同，需要重新编译" >&2
  exit 1
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
verify_tree || { echo "预编译包解压后未通过校验" >&2; exit 1; }
echo "已下载并校验预编译的 build/ffmpeg ($name)"
