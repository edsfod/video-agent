#!/usr/bin/env bash
# Builds the LGPL FFmpeg that the desktop installer ships: ffmpeg.exe and ffprobe.exe, statically linked, with dav1d
# to decode AV1 and SVT-AV1 to encode it (for `compress`), and nothing under the GPL (no x264, x265, or GPL-only filters
# such as mpdecimate). Video Agent runs them as
# separate programs. Run it in an MSYS2 UCRT64 shell with the packages listed in .github/actions/ffmpeg/action.yml; it
# writes build/ffmpeg/, keeping dav1d, SVT-AV1 and FFmpeg's unpacked source in build/ffmpeg-deps and build/ffmpeg-work
# for the next run. The LGPL requires the corresponding source, so the exact tarballs land in build/ffmpeg/source
# and go onto every release beside the installer (see docs/design/distribution.md).
# After changing this file, publish the new prebuilt build (docs/development.md, 构建). Comments go on lines of their
# own: fetch.sh hashes the other lines.
set -euo pipefail

FFMPEG_VERSION=9.0.2
FFMPEG_SHA256=8c3850283eb25fa026482078a04051e0be17347b09ef81a0849bec15a96e002e
DAV1D_VERSION=1.5.4
DAV1D_SHA256=686616b7c69eb88d44459391ab25cac13b6647a3b288835c5784e71c1514a5c5
SVTAV1_VERSION=4.2.0
SVTAV1_SHA256=c7b13c4a84bd3751aa35fcc72be13e6875467e7c2216879251a486e5b1e4e740

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
OUT=$ROOT/build/ffmpeg
WORK=$ROOT/build/ffmpeg-work
DEPS=$ROOT/build/ffmpeg-deps

# fetch URL SHA256 FOLDER: downloads a source tarball into FOLDER unless it is there already, and checks it.
fetch() {
  local file="$3/$(basename "$1")"
  [ -f "$file" ] || curl -sSfL --retry 3 "$1" -o "$file"
  echo "$2  $file" | sha256sum -c -
}

# With ccache installed, every compiler call goes through it, so a rebuild with the same compiler reuses the objects of
# the last one and only compiles what changed (the CI keeps the ccache folder in the Actions cache).
CC=gcc
LAUNCHER=()
if command -v ccache >/dev/null; then
  CC="ccache gcc"
  LAUNCHER=(-DCMAKE_C_COMPILER_LAUNCHER=ccache -DCMAKE_CXX_COMPILER_LAUNCHER=ccache)
fi

# dav1d and SVT-AV1 as static libraries, installed into build/ffmpeg-deps with their source tarballs and licences. Built
# again only when deps_key changes (the CI keeps the folder in the Actions cache): with ccache they still took about two
# minutes, as their assembly does not go through it.
build_deps() {
  local work=$WORK/deps
  rm -rf "$DEPS" "$work"
  mkdir -p "$DEPS/source" "$DEPS/licenses" "$work"
  fetch "https://downloads.videolan.org/pub/videolan/dav1d/$DAV1D_VERSION/dav1d-$DAV1D_VERSION.tar.xz" "$DAV1D_SHA256" \
    "$DEPS/source"
  fetch "https://gitlab.com/AOMediaCodec/SVT-AV1/-/archive/v$SVTAV1_VERSION/SVT-AV1-v$SVTAV1_VERSION.tar.gz" \
    "$SVTAV1_SHA256" "$DEPS/source"
  tar -xf "$DEPS/source/dav1d-$DAV1D_VERSION.tar.xz" -C "$work"
  tar -xf "$DEPS/source/SVT-AV1-v$SVTAV1_VERSION.tar.gz" -C "$work"
  # dav1d without its tools and tests.
  CC="$CC" meson setup "$work/dav1d-build" "$work/dav1d-$DAV1D_VERSION" --prefix="$DEPS/prefix" --libdir=lib \
    --default-library=static --buildtype=release -Denable_tools=false -Denable_tests=false
  ninja -C "$work/dav1d-build" install
  # SVT-AV1 without its command-line encoder. Without link-time optimization: by default its objects hold only GCC LTO
  # bytecode, so linking ffmpeg and ffprobe compiled SVT-AV1 again each time (over 4 minutes on the CI machines; a
  # second or two without it), and the encoder was no faster with it.
  cmake -S "$work/SVT-AV1-v$SVTAV1_VERSION" -B "$work/svtav1-build" -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="$DEPS/prefix" -DCMAKE_INSTALL_LIBDIR=lib -DBUILD_SHARED_LIBS=OFF -DBUILD_APPS=OFF \
    -DBUILD_TESTING=OFF -DSVT_AV1_LTO=OFF "${LAUNCHER[@]}"
  ninja -C "$work/svtav1-build" install
  cp "$work/dav1d-$DAV1D_VERSION/COPYING" "$DEPS/licenses/dav1d-COPYING.txt"
  cp "$work/SVT-AV1-v$SVTAV1_VERSION/LICENSE.md" "$DEPS/licenses/SVT-AV1-LICENSE.md"
  cp "$work/SVT-AV1-v$SVTAV1_VERSION/PATENTS.md" "$DEPS/licenses/SVT-AV1-PATENTS.md"
  rm -rf "$work"
  deps_key >"$DEPS/DEPS-KEY"
}

# What build_deps makes depends on: its commands (bash prints the functions without comments), the versions it builds
# and GCC's major version. Static C libraries from an earlier GCC of the same major version link fine, so a minor GCC
# update on the CI does not rebuild them.
deps_key() {
  {
    declare -f fetch build_deps
    echo "$DAV1D_VERSION $DAV1D_SHA256 $SVTAV1_VERSION $SVTAV1_SHA256"
    gcc -dumpfullversion | cut -d. -f1
  } | sha256sum | cut -d' ' -f1
}

# The CI asks for the key to restore the folder before building.
if [ "${1:-}" = --deps-key ]; then
  deps_key
  exit 0
fi

rm -rf "$OUT/bin" "$WORK/ffmpeg-build"
mkdir -p "$OUT/source" "$OUT/bin" "$OUT/licenses" "$WORK"
[ "$(cat "$DEPS/DEPS-KEY" 2>/dev/null)" = "$(deps_key)" ] || build_deps
cp "$DEPS"/source/* "$OUT/source/"
cp "$DEPS"/licenses/* "$OUT/licenses/"

# FFmpeg's source is unpacked once and built out of tree, which leaves the source folder as it is, so a rebuild does not
# unpack it again.
fetch "https://ffmpeg.org/releases/ffmpeg-$FFMPEG_VERSION.tar.xz" "$FFMPEG_SHA256" "$OUT/source"
SRC=$WORK/ffmpeg-$FFMPEG_VERSION
if [ "$(cat "$SRC/UNPACKED" 2>/dev/null)" != "$FFMPEG_SHA256" ]; then
  rm -rf "$SRC"
  tar -xf "$OUT/source/ffmpeg-$FFMPEG_VERSION.tar.xz" -C "$WORK"
  echo "$FFMPEG_SHA256" >"$SRC/UNPACKED"
fi

# FFmpeg: LGPL (no --enable-gpl, no --enable-nonfree), no autodetected system libraries, static. Everything native
# stays in (decoders, demuxers, muxers, filters); only zlib, dav1d and SVT-AV1 come from outside.
CONFIGURE=(
  --disable-debug --disable-doc --disable-ffplay
  --disable-shared --enable-static --pkg-config-flags=--static --extra-ldflags=-static
  --disable-autodetect --enable-zlib --enable-libdav1d --enable-libsvtav1
  --disable-network --disable-devices --disable-hwaccels
)
mkdir -p "$WORK/ffmpeg-build"
cd "$WORK/ffmpeg-build"
# configure runs with plain gcc: its 1100-odd test compiles are tiny, and going through ccache only added a process to
# each (about a minute in all); make gets ccache instead.
PKG_CONFIG_PATH="$DEPS/prefix/lib/pkgconfig" "$SRC/configure" "${CONFIGURE[@]}"
make -j"$(nproc)" CC="$CC"
cp ffmpeg.exe ffprobe.exe "$OUT/bin/"
strip "$OUT/bin/ffmpeg.exe" "$OUT/bin/ffprobe.exe"

# Licences of what is inside: FFmpeg (LGPL 2.1 or later), dav1d (BSD 2-clause), SVT-AV1 (BSD 3-clause clear, with
# the Alliance for Open Media patent licence; copied with build_deps), zlib.
cp "$SRC/COPYING.LGPLv2.1" "$OUT/licenses/FFmpeg-LGPL-2.1.txt"
cp "$SRC/LICENSE.md" "$OUT/licenses/FFmpeg-LICENSE.md"
cp "${MINGW_PREFIX:-/ucrt64}/share/licenses/zlib/LICENSE" "$OUT/licenses/zlib-LICENSE.txt"

# Fail here, not in the installer: the build must be LGPL and have what Video Agent uses.
bin="$OUT/bin/ffmpeg.exe"
"$bin" -hide_banner -L | grep -q 'GNU Lesser General Public' || { echo 'not an LGPL build' >&2; exit 1; }
for kind_name in filters:freezedetect filters:tblend filters:drawbox filters:tile filters:select decoders:libdav1d \
  decoders:hevc decoders:h264 encoders:mjpeg encoders:aac encoders:mpeg4 encoders:srt encoders:libsvtav1; do
  "$bin" -hide_banner -"${kind_name%%:*}" | grep -qw "${kind_name#*:}" || { echo "missing ${kind_name}" >&2; exit 1; }
done

{
  echo "FFmpeg $FFMPEG_VERSION (sha256 $FFMPEG_SHA256) with dav1d $DAV1D_VERSION (sha256 $DAV1D_SHA256)" \
    "and SVT-AV1 $SVTAV1_VERSION (sha256 $SVTAV1_SHA256)"
  echo "Built by packaging/ffmpeg/build.sh in MSYS2 UCRT64; zlib from MSYS2."
  echo "configure ${CONFIGURE[*]}"
  "$bin" -hide_banner -version | head -1
} > "$OUT/BUILD.txt"
cat "$OUT/BUILD.txt"
