; Kura's additions to the Tauri installer. See docs/stack/tauri.md, "Installer".

; 1. Program files go to %LOCALAPPDATA%\Programs\Kura, where Windows keeps programs
;    installed for one person. Tauri's default, %LOCALAPPDATA%\Kura, is Kura's data
;    folder, and program files and data must never share a folder.
!define MUI_CUSTOMFUNCTION_GUIINIT KuraUseProgramsFolder
Function KuraUseProgramsFolder
    ${If} $INSTDIR == "$LOCALAPPDATA\Kura"
        StrCpy $INSTDIR "$LOCALAPPDATA\Programs\Kura"
    ${EndIf}
FunctionEnd

; 2. The page after the welcome is Kura's "before you install" text (scripts/installer-notes.mjs):
;    everything Kura downloads to the PC, then its MIT licence. NSIS shows it as a licence page;
;    these say what it is instead of NSIS's words for a licence agreement.
!define MUI_LICENSEPAGE_TEXT_TOP "What Kura downloads to this PC, then its licence. Scroll to read it all."
!define MUI_LICENSEPAGE_TEXT_BOTTOM "Kura is free software under the MIT licence. Click I Agree to install it."

; 3. Before anything is removed, offer to export Kura's data to Documents.
;    If the export fails, nothing is removed.
!macro NSIS_HOOK_PREUNINSTALL
    ${If} $UpdateMode <> 1
    ${AndIfNot} ${Silent}
        ${If} ${Cmd} `MessageBox MB_YESNO|MB_ICONQUESTION "Export your Kura data before uninstalling?$\r$\n$\r$\nKura saves one zip in your Documents folder. Your anime files are never touched." IDYES`
            nsExec::ExecToStack '"$INSTDIR\engine\kura-engine.exe" export "$DOCUMENTS"'
            Pop $0 ; exit code
            Pop $1 ; what the engine said
            ${If} $0 == 0
                MessageBox MB_OK|MB_ICONINFORMATION "$1"
            ${Else}
                MessageBox MB_OK|MB_ICONSTOP "The export didn't work, so Kura was not removed.$\r$\n$\r$\n$1"
                Abort
            ${EndIf}
        ${EndIf}
    ${EndIf}
!macroend

; 4. Kura's data folder stays unless "Delete the application data" was ticked. Data moved to
;    another drive goes too (the data folder's location.txt says where, in UTF-16 so any path's
;    letters read right), but only Kura's own parts of it, and its folder only if nothing else is
;    left there: never anyone's other files.
!macro KuraDeleteData HOME
    ClearErrors
    FileOpen $0 "${HOME}\location.txt" r
    ${IfNot} ${Errors}
        FileReadUTF16LE $0 $1
        FileClose $0
        ${If} $1 != ""
        ${AndIf} ${FileExists} "$1\kura.db"
            Delete "$1\kura.db"
            Delete "$1\kura.db-wal"
            Delete "$1\kura.db-shm"
            Delete "$1\credentials.json"
            Delete "$1\move.txt"
            Delete "$1\stopping.txt"
            RMDir /r "$1\artwork"
            RMDir /r "$1\backups"
            RMDir /r "$1\cache"
            RMDir /r "$1\logs"
            RMDir /r "$1\tools"
            RMDir "$1"
        ${EndIf}
    ${EndIf}
    RMDir /r "${HOME}"
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
    ; What an install couldn't remove of an old engine (see 5), then Kura's folder if that was
    ; all that kept it.
    RMDir /r "$INSTDIR\engine-old"
    RMDir "$INSTDIR"
    ${If} $DeleteAppDataCheckboxState = 1
    ${AndIf} $UpdateMode <> 1
        !insertmacro KuraDeleteData "$LOCALAPPDATA\Kura"
    ${EndIf}
!macroend

; 5. An update brings a whole new engine. NSIS copies the new version's files over the old ones
;    but leaves the ones the new version doesn't have, and Python then finds both versions of
;    what changed: updated to 0.2.0, the engine still said 0.1.0, reading the old version's
;    record beside its own. So the old engine is set aside before the new one is copied into a
;    folder of its own, and removed once the new one is in. If the install stops before then,
;    the old engine goes back. An old engine still stopping gets a few seconds to let go of its
;    files; anything it still holds goes at the next install, or with Kura.
!macro NSIS_HOOK_PREINSTALL
    RMDir /r "$INSTDIR\engine-old" ; what an earlier install couldn't remove
    !insertmacro KuraTryUntilGone 'Rename "$INSTDIR\engine" "$INSTDIR\engine-old"' "$INSTDIR\engine"
!macroend

!macro NSIS_HOOK_POSTINSTALL
    !insertmacro KuraTryUntilGone 'RMDir /r "$INSTDIR\engine-old"' "$INSTDIR\engine-old"
!macroend

Function .onInstFailed
    ${If} ${FileExists} "$INSTDIR\engine-old\*.*"
        RMDir /r "$INSTDIR\engine"
        Rename "$INSTDIR\engine-old" "$INSTDIR\engine"
    ${EndIf}
FunctionEnd

; Does ACTION until FOLDER is gone, at most 10 times, half a second apart.
!macro KuraTryUntilGone ACTION FOLDER
    Push $R9
    StrCpy $R9 0
    ${DoWhile} ${FileExists} "${FOLDER}\*.*"
        ${If} $R9 >= 10
            ${ExitDo}
        ${EndIf}
        ${If} $R9 > 0
            Sleep 500
        ${EndIf}
        ${ACTION}
        IntOp $R9 $R9 + 1
    ${Loop}
    Pop $R9
!macroend
