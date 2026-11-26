<!--
类别：状态 · 决策层。读者：想知道「为什么不用另一种做法」的人和 AI。
决策被推翻时原地改写本文，被推翻的方案和失败的依据写进「备选方案」。不写状态和日期：仓库里的 ADR 都是当前有效的，时间看 git。
-->

# ADR-0011: DeepSeek 网页版由桌面程序在窗口里操作官方页面

## 背景

- DeepSeek 网页版要能全自动写总结（`SUM-02`）。

## 决策

桌面程序在自己的窗口里像人一样用 chat.deepseek.com：用户在里面登录一次，登录状态存在它自己的会话里；程序附文件、输入、发送，读回答里的代码块。做法见 [routes-design.md](../routes-design.md)「DeepSeek 网页版」。

## 备选方案

1. **用逆向的接口**：那些项目自己提醒会被封号。

## 影响

- 页面一变，程序就要跟着改；页面的实测行为见 [reference/deepseek-web.md](../reference/deepseek-web.md)。
- 要自己处理限流、繁忙和上传失败；所有窗口的消息之间至少隔 1 分钟。
- 窗口被遮住或在屏幕外时也要绘制，所以程序关掉 Chromium 的 `CalculateNativeWinOcclusion`。
