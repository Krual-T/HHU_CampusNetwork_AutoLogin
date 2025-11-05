param (
    [string] $TaskName,
    [string] $ExePath,
    [string] $NetworkName
)

$ErrorActionPreference = "Stop"

try {
    $action = New-ScheduledTaskAction -Execute $ExePath
    $class = cimclass MSFT_TaskEventTrigger root/Microsoft/Windows/TaskScheduler
    $trigger = $class | New-CimInstance -ClientOnly
    $trigger.Enabled = $True
    $trigger.Subscription = '<QueryList><Query Id="0" Path="Microsoft-Windows-NetworkProfile/Operational"><Select Path="Microsoft-Windows-NetworkProfile/Operational">*[System[Provider[@Name=''Microsoft-Windows-NetworkProfile''] and EventID=10000]]</Select></Query></QueryList>'

    $settings = New-ScheduledTaskSettingsSet -RunOnlyIfNetworkAvailable -NetworkName $NetworkName  -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries -WakeToRun

    $principal = New-ScheduledTaskPrincipal -GroupId "S-1-5-32-544" -RunLevel Highest

    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force
    
    Write-Host "SUCCESS: Scheduled task created/updated."
    exit 0
}
catch {
    Write-Error "FAILURE: $($_.Exception.Message)"
    exit 1
}