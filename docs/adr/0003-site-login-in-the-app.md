<!--
类别：状态 · 决策层。读者：想知道「为什么不用另一种做法」的人和 AI。
决策被推翻时原地改写本文，被推翻的方案和失败的依据写进「备选方案」。不写状态和日期：仓库里的 ADR 都是当前有效的，时间看 git。
-->

# ADR-0003: 网站在桌面程序里登录，登录状态以临时 cookie 文件交给 yt-dlp

## 背景

- 要登录才给的字幕要能下载（`SRC-02`）：B 站只对登录的账号列出字幕，包括 AI 字幕。
- 下载由 yt-dlp 做（[processing-design.md](../processing-design.md)「下载」）。

## 决策

1. 用户在桌面程序里登录网站：每个网站一个持久分区，打包后的程序开着 Electron 的 `enableCookieEncryption`，cookie 用 DPAPI 加密保存。
2. 每次下载时，主进程把该网站的 cookie 写成 Netscape 格式的临时文件，用 `download --cookies` 交给命令行；任务结束和程序启动时删掉。
3. 命令行只接受 `--cookies FILE`，从不自己读浏览器。
4. 「从浏览器导入…」是补充手段：经 yt-dlp 的 `--cookies-from-browser` 读已装的浏览器，或导入 cookies.txt。

## 备选方案

1. **让 yt-dlp 每次直接从浏览器读 cookie**：Edge 开着时它的数据库被锁；Chromium 127 以后的应用绑定加密，yt-dlp 解不开（实测 2026-10-27）。

## 影响

- 只用命令行的人要自己给 cookies 文件。
- 真实登录（尤其 Google）和用它下载没有自动测试，要用户的账号（[development.md](../development.md)「已知问题」）。
