# Decision records

Why Video Agent is built as it is: what the user decided or asked for, what Claude decided (marked `Claude judgment`), when, and what was measured or tried on the way. One file per topic; a topic's later entries revise its earlier ones. How the parts fit together now is in [ARCHITECTURE.md](../../ARCHITECTURE.md), and how each release was checked in [release-log.md](../release-log.md).

These were sections of ARCHITECTURE.md until 2026-10-29, when an outside review of 0.9.2-beta found that file to be decision records, a release log and an outdated status in one (user request to restructure it). The text was moved as it was. Code comments still cite the old section names, as in `ARCHITECTURE.md, "Concurrent jobs"`; the first column gives the file for each.

| Section | File | Decided |
| --- | --- | --- |
| Platform, Product boundary, Parts, Interface sequence, First implementation boundary | [scope.md](scope.md) | user, 2026-10-26 and 2026-10-27 |
| Downloader decision | [downloader.md](downloader.md) | Claude judgment |
| Site subtitles and Bilibili login | [site-accounts.md](site-accounts.md) | user, 2026-10-27 and 2026-10-29 |
| Collections | [collections.md](collections.md) | user, 2026-10-28 |
| BCut client | [bcut.md](bcut.md) | user, 2026-10-28 |
| Summary versions | [summary-versions.md](summary-versions.md) | user request, 2026-10-28 |
| Other agents and chat AIs with a file limit | [other-agents.md](other-agents.md) | user requests, 2026-10-28 and 2026-10-29 |
| Evidence for weaker chat AIs, local subtitles, folder names | [chat-ai-evidence.md](chat-ai-evidence.md) | user requests, 2026-10-28 |
| Cleaned transcript | [cleaned-transcript.md](cleaned-transcript.md) | user, 2026-10-28 |
| Layout and screen pages | [layout-and-screen-pages.md](layout-and-screen-pages.md) | user, 2026-10-27 and 2026-10-28 |
| Summary depth | [summary-depth.md](summary-depth.md) | user, 2026-10-27 and 2026-10-28 |
| Summary templates | [summary-templates.md](summary-templates.md) | user, 2026-10-27 and 2026-10-29 |
| Skill steps in code | [skill-steps.md](skill-steps.md) | user request, 2026-10-29 |
| Concurrent jobs | [concurrent-jobs.md](concurrent-jobs.md) | user, 2026-10-27 |
| GUI | [gui.md](gui.md) | user; Claude judgment on technology |
| Distribution | [distribution.md](distribution.md) | user, 2026-10-27 |
| Compression | [compression.md](compression.md) | user, 2026-10-28 |
| Bundled FFmpeg | [bundled-ffmpeg.md](bundled-ffmpeg.md) | user, 2026-10-28 |
| Updates | [updates.md](updates.md) | user, 2026-10-27 to 2026-10-29 |
| Licence and privacy in the installer | [licence-and-privacy.md](licence-and-privacy.md) | user request, 2026-10-29 |
| Development, tests and CI | [development.md](development.md) | user, 2026-10-27 to 2026-10-29 |
| Front-end types | [front-end-types.md](front-end-types.md) | user, 2026-10-29, on Claude's proposal |
