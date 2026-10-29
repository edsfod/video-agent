# Licence and privacy in the installer — user request (2026-10-29)

Until 0.9.3 the installer put `resources\LICENSE.txt` and `THIRD-PARTY-NOTICES.txt` in the installation folder but showed neither, and the privacy notes and terms of use were only in the README. The user asked for all three of these:

- **`PRIVACY.md`** holds the privacy notes and terms of use, moved from the README (which links to it), and a short licence summary that points to the full texts.
- **Licence page.** The installer shows it first. `packaging/notices.py` writes it as plain text to `build/PRIVACY.txt`, with a byte order mark (NSIS reads a text file as UTF-8 only after one, otherwise in the system code page) and CRLF line ends, and the installer also leaves it in the installation folder. Updates and silent installs skip the page. It has electron-builder's 我同意 button (Claude judgment: the AGPL needs no acceptance, but the terms of use are agreed to there).
- **设置 → 关于** shows the version and licence, opens PRIVACY.md in a dialog, and opens the licence and the third-party notices in the default editor.
