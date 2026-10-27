; Put the bundled CLI (resources\cli) on the user's PATH, so terminals and Agents can run `video-agent`
; without the desktop app. The uninstaller runs customUnInstall before it deletes $INSTDIR, and an update runs
; the old uninstaller before customInstall, so the entry always points at the current install folder.

!macro videoAgentPath ACTION
  nsExec::ExecToLog 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\resources\user-path.ps1" ${ACTION} "$INSTDIR\resources\cli"'
  Pop $0
  ; Tell Explorer and other open programs that the environment changed; new terminals then see the PATH.
  SendMessage 0xFFFF 0x001A 0 "STR:Environment" /TIMEOUT=500
!macroend

; electron-builder keeps a copy of the installer (about 160 MB) in %LOCALAPPDATA%\<name>-updater for electron-updater,
; which this app does not use, and the uninstaller leaves it behind.
!macro videoAgentDropInstallerCopy
  Delete "$LOCALAPPDATA\${APP_INSTALLER_STORE_FILE}"
  ${GetParent} "$LOCALAPPDATA\${APP_INSTALLER_STORE_FILE}" $1
  RMDir "$1"
!macroend

!macro customInstall
  !insertmacro videoAgentPath add
  !insertmacro videoAgentDropInstallerCopy
!macroend

!macro customUnInstall
  !insertmacro videoAgentPath remove
  !insertmacro videoAgentDropInstallerCopy
!macroend
