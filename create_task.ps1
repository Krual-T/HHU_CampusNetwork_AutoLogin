param (
    [string] $TaskName,
    [string] $ExePath,
    [string] $NetworkName
)

$ErrorActionPreference = "Stop"

try {
    $exePathResolved = $ExePath.Trim("'", '"')
    $action = New-ScheduledTaskAction -Execute $exePathResolved

    $class = Get-CimClass MSFT_TaskEventTrigger root/Microsoft/Windows/TaskScheduler
    $trigger = $class | New-CimInstance -ClientOnly
    $trigger.Enabled = $True
    $trigger.Subscription = '<QueryList><Query Id="0" Path="Microsoft-Windows-NetworkProfile/Operational"><Select Path="Microsoft-Windows-NetworkProfile/Operational">*[System[Provider[@Name=''Microsoft-Windows-NetworkProfile''] and EventID=10000]]</Select></Query></QueryList>'
    $principal = New-ScheduledTaskPrincipal -UserID "NT AUTHORITY\SYSTEM" -LogonType ServiceAccount -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -RunOnlyIfNetworkAvailable -NetworkName $NetworkName  -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries -WakeToRun -MultipleInstances Parallel
    $definition = New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings -Principal $principal

    Register-ScheduledTask -TaskName $TaskName -InputObject $definition -Force
    
    Write-Host "SUCCESS: Scheduled task created/updated."
    exit 0
}
catch {
    Write-Error "FAILURE: $($_.Exception.Message)"
    exit 1
}
