; Put the bundled CLI (resources\cli) on the user's PATH, so terminals and Agents can run `video-agent`
; without the desktop app. The uninstaller runs customUnInstall before it deletes $INSTDIR, and an update runs
; the old uninstaller before customInstall, so the entry always points at the current install folder.

!macro videoAgentPath ACTION
  nsExec::ExecToLog 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\resources\user-path.ps1" ${ACTION} "$INSTDIR\resources\cli"'
  Pop $0
  ; Tell Explorer and other open programs that the environment changed; new terminals then see the PATH.
  SendMessage 0xFFFF 0x001A 0 "STR:Environment" /TIMEOUT=500
!macroend

!macro customInstall
  !insertmacro videoAgentPath add
!macroend

!macro customUnInstall
  !insertmacro videoAgentPath remove
!macroend
