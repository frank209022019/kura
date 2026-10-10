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

; 2. Before anything is removed, offer to export Kura's data to Documents.
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

; 3. Kura's data folder stays unless "Delete the application data" was ticked.
!macro NSIS_HOOK_POSTUNINSTALL
    ${If} $DeleteAppDataCheckboxState = 1
    ${AndIf} $UpdateMode <> 1
        RMDir /r "$LOCALAPPDATA\Kura"
    ${EndIf}
!macroend
