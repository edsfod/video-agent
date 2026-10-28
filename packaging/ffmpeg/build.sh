#!/usr/bin/env bash
# Builds the LGPL FFmpeg that the desktop installer ships: ffmpeg.exe and ffprobe.exe, statically linked, with dav1d
# to decode AV1 and SVT-AV1 to encode it (for `compress`), and nothing under the GPL (no x264, x265, or GPL-only filters
# such as mpdecimate). Video Agent runs them as
# separate programs. Run it in an MSYS2 UCRT64 shell with the packages listed in .github/workflows/ffmpeg.yml; it
# writes build/ffmpeg/. The LGPL requires the corresponding source, so the exact tarballs land in build/ffmpeg/source
# and go onto every release beside the installer (see ARCHITECTURE.md, "Bundled FFmpeg").
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
PREFIX=$WORK/prefix
rm -rf "$WORK" "$OUT/bin"
mkdir -p "$OUT/source" "$OUT/bin" "$OUT/licenses" "$WORK"

fetch() { # url sha256
  local file="$OUT/source/$(basename "$1")"
  [ -f "$file" ] || curl -sSfL --retry 3 "$1" -o "$file"
  echo "$2  $file" | sha256sum -c -
  tar -xf "$file" -C "$WORK"
}
fetch "https://ffmpeg.org/releases/ffmpeg-$FFMPEG_VERSION.tar.xz" "$FFMPEG_SHA256"
fetch "https://downloads.videolan.org/pub/videolan/dav1d/$DAV1D_VERSION/dav1d-$DAV1D_VERSION.tar.xz" "$DAV1D_SHA256"
fetch "https://gitlab.com/AOMediaCodec/SVT-AV1/-/archive/v$SVTAV1_VERSION/SVT-AV1-v$SVTAV1_VERSION.tar.gz" "$SVTAV1_SHA256"

# dav1d as a static library only.
meson setup "$WORK/dav1d-build" "$WORK/dav1d-$DAV1D_VERSION" --prefix="$PREFIX" --libdir=lib \
  --default-library=static --buildtype=release -Denable_tools=false -Denable_tests=false
ninja -C "$WORK/dav1d-build" install

# SVT-AV1 as a static library only, without its command-line encoder.
cmake -S "$WORK/SVT-AV1-v$SVTAV1_VERSION" -B "$WORK/svtav1-build" -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$PREFIX" -DCMAKE_INSTALL_LIBDIR=lib -DBUILD_SHARED_LIBS=OFF -DBUILD_APPS=OFF -DBUILD_TESTING=OFF
ninja -C "$WORK/svtav1-build" install

# FFmpeg: LGPL (no --enable-gpl, no --enable-nonfree), no autodetected system libraries, static. Everything native
# stays in (decoders, demuxers, muxers, filters); only zlib, dav1d and SVT-AV1 come from outside.
CONFIGURE=(
  --prefix="$PREFIX" --disable-debug --disable-doc --disable-ffplay
  --disable-shared --enable-static --pkg-config-flags=--static --extra-ldflags=-static
  --disable-autodetect --enable-zlib --enable-libdav1d --enable-libsvtav1
  --disable-network --disable-devices --disable-hwaccels
)
cd "$WORK/ffmpeg-$FFMPEG_VERSION"
PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig" ./configure "${CONFIGURE[@]}"
make -j"$(nproc)"
cp ffmpeg.exe ffprobe.exe "$OUT/bin/"
strip "$OUT/bin/ffmpeg.exe" "$OUT/bin/ffprobe.exe"

# Licences of what is inside: FFmpeg (LGPL 2.1 or later), dav1d (BSD 2-clause), SVT-AV1 (BSD 3-clause clear, with
# the Alliance for Open Media patent licence), zlib.
cp COPYING.LGPLv2.1 "$OUT/licenses/FFmpeg-LGPL-2.1.txt"
cp LICENSE.md "$OUT/licenses/FFmpeg-LICENSE.md"
cp "$WORK/dav1d-$DAV1D_VERSION/COPYING" "$OUT/licenses/dav1d-COPYING.txt"
cp "$WORK/SVT-AV1-v$SVTAV1_VERSION/LICENSE.md" "$OUT/licenses/SVT-AV1-LICENSE.md"
cp "$WORK/SVT-AV1-v$SVTAV1_VERSION/PATENTS.md" "$OUT/licenses/SVT-AV1-PATENTS.md"
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
