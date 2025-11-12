# All code and comments should be in English.
param (
    [string] $TaskName,
    [string] $ExePath,
    [string] $NetworkName
)

$ErrorActionPreference = "Stop"

try {
    $exePathResolved = $ExePath.Trim("'", '"')
    $action = New-ScheduledTaskAction -Execute $exePathResolved

    # --- Trigger 1: On Network Connection (Event 10000) ---
    # We rename your original $trigger to $eventTrigger for clarity
    $eventTriggerClass = Get-CimClass MSFT_TaskEventTrigger root/Microsoft/Windows/TaskScheduler
    $eventTrigger = $eventTriggerClass | New-CimInstance -ClientOnly
    $eventTrigger.Enabled = $True
    $eventTrigger.Subscription = '<QueryList><Query Id="0" Path="Microsoft-Windows-NetworkProfile/Operational"><Select Path="Microsoft-Windows-NetworkProfile/Operational">*[System[Provider[@Name=''Microsoft-Windows-NetworkProfile''] and EventID=10000]]</Select></Query></QueryList>'

    # --- Trigger 2: On Workstation Unlock (Session State Change) ---
    # This is the new trigger you wanted to add
    $sessionTriggerClass = Get-CimClass `
        -Namespace ROOT\Microsoft\Windows\TaskScheduler `
        -ClassName MSFT_TaskSessionStateChangeTrigger
    
    $unlockTrigger = New-CimInstance `
        -CimClass $sessionTriggerClass `
        -Property @{
        StateChange = 8  # 8 = TASK_SESSION_UNLOCK
        Enabled     = $True
    } `
        -ClientOnly
    
    # --- Combine Triggers into an Array ---
    # This is the key change: create an array holding both triggers
    $triggers = $eventTrigger, $unlockTrigger

    # --- Principal and Settings (Unchanged) ---
    $principal = New-ScheduledTaskPrincipal -UserID "NT AUTHORITY\SYSTEM" -LogonType ServiceAccount -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -RunOnlyIfNetworkAvailable -NetworkName $NetworkName  -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries -WakeToRun -MultipleInstances Parallel
    
    # --- Create Definition (Using the trigger array) ---
    # Pass the $triggers array to the -Trigger parameter
    $definition = New-ScheduledTask -Action $action -Trigger $triggers -Settings $settings -Principal $principal

    # --- Register Task (Unchanged) ---
    Register-ScheduledTask -TaskName $TaskName -InputObject $definition -Force
    
    Write-Host "SUCCESS: Scheduled task created/updated with TWO triggers."
    exit 0
}
catch {
    Write-Error "FAILURE: $($_.Exception.Message)"
    exit 1
}