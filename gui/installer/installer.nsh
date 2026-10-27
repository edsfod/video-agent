; Put the bundled CLI (resources\cli) on the user's PATH, so terminals and Agents can run `video-agent`
; without the desktop app. A page after the folder choice says so and lets the user opt out (SignPath's rule
; "announce system changes"); the choice is kept in HKCU\Software\Video Agent for updates and silent installs.
; The uninstaller runs customUnInstall before it deletes $INSTDIR, and an update runs the old uninstaller before
; customInstall, so the entry always points at the current install folder.

!define VA_KEY "Software\Video Agent"

!macro videoAgentPath ACTION
  nsExec::ExecToLog 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\resources\user-path.ps1" ${ACTION} "$INSTDIR\resources\cli"'
  Pop $0
  ; Tell Explorer and other open programs that the environment changed; new terminals then see the PATH.
  SendMessage 0xFFFF 0x001A 0 "STR:Environment" /TIMEOUT=500
!macroend

!ifndef BUILD_UNINSTALLER
  Var vaAddPath
  Var vaPathCheckbox
!endif

!macro customInit
  ; On by default; an update or reinstall keeps the earlier choice.
  StrCpy $vaAddPath 1
  ClearErrors
  ReadRegDWORD $0 HKCU "${VA_KEY}" "AddToPath"
  ${ifNot} ${Errors}
    StrCpy $vaAddPath $0
  ${endif}
!macroend

; The page and its functions are defined where electron-builder inserts this macro: this file is included before
; LogicLib and nsDialogs, which the functions need.
!macro customPageAfterChangeDir
  Page custom vaPathPageShow vaPathPageLeave

  Function vaPathPageShow
    ${if} ${isUpdated}
      Abort
    ${endif}
    !insertmacro MUI_HEADER_TEXT "命令行工具" "让终端和 Agent 也能运行 video-agent"
    nsDialogs::Create 1018
    Pop $0
    ${NSD_CreateLabel} 0 0 100% 56u "安装程序自带命令行工具 video-agent。勾选后，会把它所在的文件夹加到当前用户 PATH 环境变量的末尾：新开的终端里可以直接运行 video-agent，Claude Code、Codex 的插件也会用它。卸载时会从 PATH 里移除。"
    Pop $0
    ${NSD_CreateCheckbox} 0 62u 100% 12u "把 video-agent 加入 PATH（推荐）"
    Pop $vaPathCheckbox
    ${if} $vaAddPath == 1
      ${NSD_Check} $vaPathCheckbox
    ${endif}
    nsDialogs::Show
  FunctionEnd

  Function vaPathPageLeave
    ${NSD_GetState} $vaPathCheckbox $vaAddPath
  FunctionEnd
!macroend

!macro customInstall
  WriteRegDWORD HKCU "${VA_KEY}" "AddToPath" $vaAddPath
  ${if} $vaAddPath == 1
    !insertmacro videoAgentPath add
  ${else}
    !insertmacro videoAgentPath remove
  ${endif}
!macroend

; electron-builder keeps a copy of the installer (about 160 MB) in %LOCALAPPDATA%\<name>-updater; electron-updater
; downloads only the blocks that differ from it, and keeps downloaded updates beside it. The uninstaller leaves the
; folder behind, so remove it here, except during an update, when the new installer runs from that folder.
!macro customUnInstall
  !insertmacro videoAgentPath remove
  ${ifNot} ${isUpdated}
    ${GetParent} "$LOCALAPPDATA\${APP_INSTALLER_STORE_FILE}" $1
    RMDir /r "$1"
    DeleteRegKey HKCU "${VA_KEY}"
  ${endIf}
!macroend
