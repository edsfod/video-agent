<!--
类别：状态 · 决策层。读者：想知道「为什么不用另一种做法」的人和 AI。
决策被推翻时原地改写本文，被推翻的方案和失败的依据写进「备选方案」。不写状态和日期：仓库里的 ADR 都是当前有效的，时间看 git。
-->

# ADR-0001: 桌面程序用 Electron，代码是经 JSDoc 检查的 JavaScript

## 背景

- 桌面程序要有内嵌终端，能跑 PowerShell、Git Bash 和交互式的 `claude`、`codex`（`APP-03`）。
- 主进程和页面的每个文件都不大；页面从 `file://` 加载 ES 模块，没有构建步骤。

## 决策

1. 用 Electron；终端用 xterm.js 和 node-pty（VS Code 在 Windows 上用的组合，经 ConPTY）。
2. 代码写 JavaScript，不编译。`tsc` 借 JSDoc 检查主进程和页面的全部代码，开严格模式和空值检查（`npm run typecheck`）。

## 备选方案

1. **Qt**：没有维护中的终端组件。
2. **改写成 TypeScript（`.ts` 文件）**：打包和测试要多一个编译步骤；JSDoc 加 `tsc` 已经给出同样的严格检查。

## 影响

- 安装包带着 Chromium。
- 类型错误在 `npm run typecheck` 时才发现；`catch` 到的错误是 `any`，参数不要求都标类型。
- 页面和主进程之间的接口类型写在 `gui/src/va.d.ts`，`preload.js` 照它检查。
