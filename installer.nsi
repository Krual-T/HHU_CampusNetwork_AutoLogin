; ---------------------------------
; HohaiAutoLogin Installer Script (V2)
; (Includes custom page for user credentials)
; ---------------------------------

; --- 1. Basic Information ---
!define APP_NAME "HohaiAutoLogin"
!define APP_VERSION "1.1" ; (Version bump)
!define EXE_NAME "HohaiAutoLogin.exe"
!define ENV_TEMPLATE_NAME ".env.example" ; (Use template)
!define ENV_CONFIG_NAME ".env"         ; (Create actual config)

Name "${APP_NAME} ${APP_VERSION}"
OutFile "HohaiAutoLogin_Setup.exe"
InstallDir "$PROGRAMFILES64\${APP_NAME}"
RequestExecutionLevel admin

; --- 2. Interface and Pages ---
!include "MUI2.nsh"
!include "nsDialogs.nsh"

; Define variables to store user input
Var USERNAME
Var PASSWORD

; Define page order
Page directory    
Page custom CustomPageCreate CustomPageLeave ; (This is our new page)
Page components   
Page instfiles    

UninstPage uninstConfirm 
UninstPage instfiles      

; --- 3. Custom Page for Credentials ---

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
    goto EndValidation

ShowError:
    MessageBox MB_OK|MB_ICONEXCLAMATION "Student ID and password cannot be empty!"
    Abort ; (Stops the user from proceeding)

EndValidation:
    ; (Validation passed)
FunctionEnd


; --- 4. Sections (Components) ---

Section "Main Application (Required)" SEC_APP
    SectionIn RO 
    SetOutPath $INSTDIR
    
    ; --- A. Install files ---
    ; 1. Install the .exe
    File "dist\${EXE_NAME}"
    ; 2. Install the template (we'll rename/modify it next)
    File "${ENV_TEMPLATE_NAME}"
    
    ; --- B. Create .env from template and user input ---
    
    ; Rename .env.example to .env
    Rename "$INSTDIR\${ENV_TEMPLATE_NAME}" "$INSTDIR\${ENV_CONFIG_NAME}"
    
    ; Read the new .env file, replace the placeholder username, and write it back
    ; $USERNAME and $PASSWORD vars hold what the user typed on the custom page
    
    ; Replace username placeholder
    nsExec::ExecToStack 'powershell -Command "(Get-Content -Path \"$INSTDIR\${ENV_CONFIG_NAME}\") -replace \"your_username_goes_here\", \"$USERNAME\" | Set-Content -Path \"$INSTDIR\${ENV_CONFIG_NAME}\""'    

    ; Replace password placeholder
    nsExec::ExecToStack 'powershell -Command "(Get-Content -Path \"$INSTDIR\${ENV_CONFIG_NAME}\") -replace \"your_password_goes_here\", \"$PASSWORD\" | Set-Content -Path \"$INSTDIR\${ENV_CONFIG_NAME}\""'

    ; --- C. Create Uninstaller and Registry ---
    WriteUninstaller "$INSTDIR\uninstall.exe"
    
    ; --- Add/Remove Programs Registry ---
    ; Creates an entry so the app appears in "Add or remove programs"
    
    ; This is the main name shown
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
                   "DisplayName" "${APP_NAME} (Auto Login)"
                   
    ; This is the path to the uninstaller
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
                   "UninstallString" "$INSTDIR\uninstall.exe"
                   
    ; This is the version number
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
                   "DisplayVersion" "${APP_VERSION}"
                   
    ; This is the application icon
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
                   "DisplayIcon" "$INSTDIR\${EXE_NAME}"

    ; --- [!!] NEW: Author Information [!!] ---
    
    ; This sets the "Publisher" field
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
                   "Publisher" "Krual" ;
                   
    ; This creates a support link (we use "mailto:" for email)
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
                   "URLInfoAbout" "https://github.com/Krual-T" ;

    ; (This is an optional field for direct email display)
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
                   "Contact" "shaokun.tang@outlook.com" ;
    
SectionEnd

Section "Run automatically on network connection" SEC_AUTORUN

    GetFullPathName /SHORT $R1 "$PROGRAMFILES64" 

    StrCpy $R2 "$R1\${APP_NAME}\${EXE_NAME}"

    StrCpy $0 `powershell -ExecutionPolicy Bypass -NonInteractive -Command "schtasks /Create /TN \"${APP_NAME}\" /TR \"$R2\" /SC ONEVENT /EC Microsoft-Windows-NetworkProfile/Operational /MO '*[System[Provider[@Name=''Microsoft-Windows-NetworkProfile''] and EventID=10000]]' /RL HIGHEST /F"`

    nsExec::ExecToStack $0
    
    Pop $R1
    Pop $R0
    
    StrCmp $R0 0 ExecutionSuccess 

    MessageBox MB_OK|MB_ICONEXCLAMATION "msg: $R0\nPowerShell output:\n$R1"
    goto EndSectionLabel 

ExecutionSuccess:
    ; 任务创建成功
    
EndSectionLabel: 
    
SectionEnd

; --- 5. Post-Installation Function ---
Function .onInstSuccess
    ; We no longer need the old pop-up message
    ; The user has already entered their info.
    ; We can show a simpler success message.
    MessageBox MB_OK|MB_ICONINFORMATION \
    "$\r$\n$\r$\n${APP_NAME} has been installed! $\r$\n(If you select $\`Run automatically$\`, it will take effect the next time you connect to the network.)"
FunctionEnd

; --- 6. Uninstaller Section ---
Section "Uninstall"
    
    nsExec::Exec 'powershell -Command "schtasks /Delete /TN \"${APP_NAME}\" /F"'
    Pop $0
    
    Delete "$INSTDIR\${EXE_NAME}"
    Delete "$INSTDIR\${ENV_CONFIG_NAME}" ; (Delete .env)
    Delete "$INSTDIR\uninstall.exe"
    RMDir $INSTDIR
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"
SectionEnd