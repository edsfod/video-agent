<!--
类别：状态 · 决策层。读者：想知道「为什么不用另一种做法」的人和 AI。
决策被推翻时原地改写本文，被推翻的方案和失败的依据写进「备选方案」。不写状态和日期：仓库里的 ADR 都是当前有效的，时间看 git。
-->

# ADR-0005: 安装包里的 FFmpeg 由本项目按 LGPL 编译

## 背景

- 安装包装完就能用，自带 FFmpeg（`INS-01`）。
- 分发 FFmpeg 的二进制，就要按它的许可证附上源码。

## 决策

1. 用 `packaging/ffmpeg/build.sh` 按 LGPL 编译 FFmpeg（用户定）：不开 `--enable-gpl`；所有原生的解码器、编码器、封装和滤镜都保留（用户定）。具体的版本、依赖和编译选项见 [distribution-design.md](../distribution-design.md)「自带的 FFmpeg」。
2. 每次发布附上 FFmpeg 和它的依赖的源码包，以及 `FFmpeg-BUILD.txt`。
3. 用 pip 或 uv 安装命令行的人，用自己从 PyPI 取得的 `imageio-ffmpeg`，本项目不分发它。

## 备选方案

1. **安装包里放 `imageio-ffmpeg` 带的 FFmpeg**：它是 GPLv3 构建（含 x264、x265）；安装包曾这样分发，没有附上源码。
2. **只编进用到的解码器和滤镜**：用户的视频是什么格式无法预知；程序以后用到别的滤镜或编码器时，还要改 `build.sh` 并重新冷编译。

## 影响

- 只能用 LGPL 构建里有的功能：找屏幕页用 `freezedetect`，不用只有 GPL 才有的 `mpdecimate`；给 AutoSlides Extractor 的裁剪视频用 FFmpeg 自己的 MPEG-4 编码器，不用 x264；压缩不能用 x265（[ADR-0006](0006-svt-av1.md)）。
- `build.sh` 的版本或编译命令改了以后要重新编译，并换上新的预编译包（[development.md](../development.md)「构建」）。
- ARCHITECTURE.md 不变量 `C6`。
