; ---------------------------------
; HohaiAutoLogin Installer Script (V2.1 - Beautified)
; ---------------------------------
Unicode true
; --- 1. Basic Information ---
!define APP_NAME "HohaiAutoLogin"
!define APP_VERSION "v1.4.0"
!define EXE_NAME "HohaiAutoLogin.exe"
!define AutoTaskScript "create_task.ps1"
!define ENV_TEMPLATE_NAME ".env.example"
!define ENV_CONFIG_NAME ".env"
!define NETWORK_NAME "Hohai University" 

Name "${APP_NAME} ${APP_VERSION}"
OutFile "HohaiAutoLogin_${APP_VERSION}_Setup.exe"
InstallDir "$PROGRAMFILES64\${APP_NAME}"
RequestExecutionLevel admin

; --- 2. Includes ---
!pragma warning disable 6001 ; Disable "mui.Header.Text not used" warning
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "nsDialogs.nsh"

; --- 3. Interface Settings (Beautification) ---

; --- Set Installer Icons ---
; (Uses modern built-in icons. Replace with your own .ico files if you have them)
!define MUI_ICON "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"

; --- Set Header Image ---
; (Uses built-in header. Replace with your own .bmp file if you have one)
; [!!] We are commenting these lines out because the .bmp file is optional and may not exist on your system [!!]
; !define MUI_HEADERIMAGE
; !define MUI_HEADERIMAGE_BITMAP "${NSISDIR}\Contrib\Graphics\Header\modern.bmp"
; !define MUI_HEADERIMAGE_RIGHT ; (Align to the right)

; --- Welcome Page ---
!insertmacro MUI_PAGE_WELCOME

; --- Pages (from your script) ---
!insertmacro MUI_PAGE_DIRECTORY
Page custom CustomPageCreate CustomPageLeave ; (This is our new page)
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES

; --- Finish Page ---
!define MUI_FINISHPAGE_RUN "$INSTDIR\${EXE_NAME}" ; Add "Run..." checkbox
!insertmacro MUI_PAGE_FINISH

; --- Uninstaller Pages ---
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; --- Language ---
!insertmacro MUI_LANGUAGE "English"

; --- 4. Variables ---
Var USERNAME
Var PASSWORD
Var SERVICE_DROPLIST        ; Handle for the dropdown list
Var SERVICE_NAME            ; String to store the final service name
; --- 5. Custom Page for Credentials ---

Function CustomPageCreate
    ; This function creates the custom page
    nsDialogs::Create 1018
    Pop $0 ; (Page handle)

    ; Page Title
    ${NSD_CreateLabel} 0 0 100% 12u "Enter your personal information for the campus network"
    Pop $1

    ; --- Username ---
    ${NSD_CreateLabel} 0 30u 100% 8u "Campus network account (student ID):"
    Pop $1
    ${NSD_CreateText} 0 40u 100% 12u ""
    Pop $USERNAME ; (Store handle in $USERNAME var)
    
    ; --- Password ---
    ${NSD_CreateLabel} 0 65u 100% 8u "Campus network password:"
    Pop $1
    ${NSD_CreatePassword} 0 75u 100% 12u ""
    Pop $PASSWORD ; (Store handle in $PASSWORD var)

    ; --- Service name ---
    ${NSD_CreateLabel} 0 100u 42% 8u "Select CampusNetwork Service name:"
    Pop $1

    ; Create the dropdown list (DropList style means user cannot type)
    ${NSD_CreateDropList} 130u 98u 20% 12u ""
    Pop $SERVICE_DROPLIST
    
    ; Add the options (Index 0, 1, 2, 3)
    ${NSD_CB_AddString} $SERVICE_DROPLIST "中国移动"
    ${NSD_CB_AddString} $SERVICE_DROPLIST "中国电信"
    ${NSD_CB_AddString} $SERVICE_DROPLIST "中国联通"
    ${NSD_CB_AddString} $SERVICE_DROPLIST "校园外网服务"
    
    ; Set default selection (index 0 for "中国移动")
    SendMessage $SERVICE_DROPLIST ${CB_SETCURSEL} 0 0
    ; Show the page
    nsDialogs::Show
FunctionEnd

Function CustomPageLeave
    ; This function runs when the user clicks "Next"
    ; We read the values from the controls and save them
    
    ${NSD_GetText} $USERNAME $USERNAME ; (Read text from $USERNAME handle back into $USERNAME var)
    ${NSD_GetText} $PASSWORD $PASSWORD ; (Read text from $PASSWORD handle back into $PASSWORD var)
    
    ; (Simple Validation)
    StrCmp $USERNAME "" ShowError ; (Jump to ShowError if username is empty)
    StrCmp $PASSWORD "" ShowError ; (Jump to ShowError if password is empty)

    SendMessage $SERVICE_DROPLIST ${CB_GETCURSEL} 0 0 $R0 ; $R0 will contain the selected index (0, 1, 2, or 3)
    
    ; Use LogicLib Switch/Case to map index to string
    ${Switch} $R0
        ${Case} 0 ; "中国移动"
            StrCpy $SERVICE_NAME "中国移动(CMCC NET)"
            ${Break}
        ${Case} 1 ; "中国电信"
            StrCpy $SERVICE_NAME "中国电信(常州)"
            ${Break}
        ${Case} 2 ; "中国联通"
            StrCpy $SERVICE_NAME "中国联通(常州)"
            ${Break}
        ${Case} 3 ; "校园外网服务"
            StrCpy $SERVICE_NAME "校园外网服务(out-campus NET)"
            ${Break}
        ${Default} ; Fallback (shouldn't happen, but good practice)
            StrCpy $SERVICE_NAME "中国移动(CMCC NET)"
            ${Break}
    ${EndSwitch}

    goto EndValidation

ShowError:
    MessageBox MB_OK|MB_ICONEXCLAMATION "Student ID and password cannot be empty!"
    Abort ; (Stops the user from proceeding)

EndValidation:
    ; (Validation passed)
FunctionEnd

; --- 6. Auto-Uninstall Function ---
Function .onInit
    ClearErrors
    
    ReadRegStr $R0 HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "UninstallString"
    
    IfErrors Done
    
    MessageBox MB_YESNO|MB_ICONQUESTION \
        "${APP_NAME} is already installed.$\n$\nDo you want to uninstall the previous version and reinstall?" \
        IDYES RunUninstaller

    Abort
    
RunUninstaller:
    ExecWait '"$R0" /S _?=$INSTDIR'
    
Done:
FunctionEnd

; --- 7. Sections (Components) ---

Section "Main Application (Required)" SEC_APP
    SectionIn RO 
    SetOutPath $INSTDIR
    
    ; --- A. Install files ---
    File "dist\${EXE_NAME}"
    File "${ENV_TEMPLATE_NAME}"
    
    ; --- B. Create .env from template and user input ---
    Rename "$INSTDIR\${ENV_TEMPLATE_NAME}" "$INSTDIR\${ENV_CONFIG_NAME}"
    
    nsExec::ExecToStack 'powershell -Command "$$content = (Get-Content -Path \"$INSTDIR\${ENV_CONFIG_NAME}\" -Encoding Utf8 -Raw); $$content = $$content.Replace(\"your_username_goes_here\", \"$USERNAME\").Replace(\"your_password_goes_here\", \"$PASSWORD\").Replace(\"your_service_name_goes_here\", \"$SERVICE_NAME\"); $$content | Set-Content -Path \"$INSTDIR\${ENV_CONFIG_NAME}\" -Encoding Utf8"'    ; --- C. Create Uninstaller and Registry ---
    WriteUninstaller "$INSTDIR\uninstall.exe"
    
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
                 "DisplayName" "${APP_NAME} (Auto Login)"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
                 "UninstallString" "$INSTDIR\uninstall.exe"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
                 "DisplayVersion" "${APP_VERSION}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
                 "DisplayIcon" "$INSTDIR\${EXE_NAME}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
                 "Publisher" "Krual"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
                 "URLInfoAbout" "https://github.com/Krual-T"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
                 "Contact" "shaokun.tang@outlook.com"
    
SectionEnd

Section "Run automatically on network connection" SEC_AUTORUN
    SetOutPath $INSTDIR
    
    File "${AutoTaskScript}"
    IfErrors PSScriptError

    ; --- [!!] FINAL BUG FIX: Added nested quotes to -ExePath [!!] ---
    ; Both -File and -ExePath now correctly handle spaces in $INSTDIR
    StrCpy $0 `powershell -ExecutionPolicy Bypass -NonInteractive -File "$INSTDIR\${AutoTaskScript}" -TaskName "${APP_NAME}" -ExePath '"$INSTDIR\${EXE_NAME}"' -NetworkName "${NETWORK_NAME}"`

    nsExec::ExecToStack $0
    
    ; (This is the correct Pop order)
    Pop $R1 ; 1. Exit Code
    Pop $R0 ; 2. Output Text

    ; Delete the script after execution
    Delete "$INSTDIR\${AutoTaskScript}"
    
    StrCmp $R1 0 ExecutionSuccess 

    MessageBox MB_OK|MB_ICONEXCLAMATION "Failed to create scheduled task!$\n$\nExit Code: $R1$\n$\nPowerShell Error:$\n$R0"
    goto EndSectionLabel 

PSScriptError:
    MessageBox MB_OK|MB_ICONEXCLAMATION "Runtime Error: Could not extract ${AutoTaskScript} to $INSTDIR."
    goto EndSectionLabel 

ExecutionSuccess:
    
EndSectionLabel: 
    
SectionEnd

; --- 8. Section Descriptions (Beautification) ---
; This adds descriptions to the Components page
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
    !insertmacro MUI_DESCRIPTION_TEXT ${SEC_APP} "Installs the main application, configuration file, and uninstaller."
    !insertmacro MUI_DESCRIPTION_TEXT ${SEC_AUTORUN} "Creates a Windows Scheduled Task to run the application automatically when you connect to the '${NETWORK_NAME}' network."
!insertmacro MUI_FUNCTION_DESCRIPTION_END


; --- 9. Post-Installation Function ---
Function .onInstSuccess
FunctionEnd

; --- 10. Uninstaller Section ---
Section "Uninstall"
    
    ; 1. Remove Scheduled Task
    nsExec::Exec 'powershell -Command "schtasks /Delete /TN \"${APP_NAME}\" /F"'
    Pop $0
    
    ; 2. Delete files
    Delete "$INSTDIR\${AutoTaskScript}"  ; (Also delete the .ps1 file just in case)
    Delete "$INSTDIR\${EXE_NAME}"
    Delete "$INSTDIR\${ENV_CONFIG_NAME}"
    Delete "$INSTDIR\uninstall.exe"
    
    ; 3. Delete directory
    RMDir $INSTDIR
    
    ; 4. Remove registry keys
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"
SectionEnd