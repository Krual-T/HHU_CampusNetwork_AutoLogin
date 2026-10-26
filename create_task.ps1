# All code and comments should be in English.
param (
    [Parameter(Mandatory = $true)][string] $TaskName,
    [Parameter(Mandatory = $true)][string] $ExePath,
    [switch] $Preview
)

$ErrorActionPreference = "Stop"
try {
    $exePathResolved = $ExePath.Trim("'", '"')
    if (-not (Test-Path -LiteralPath $exePathResolved -PathType Leaf)) {
        throw "Executable does not exist."
    }
    $exePathResolved = (Get-Item -LiteralPath $exePathResolved).FullName
    $action = New-ScheduledTaskAction -Execute $exePathResolved
    $eventClass = Get-CimClass MSFT_TaskEventTrigger root/Microsoft/Windows/TaskScheduler
    $eventTrigger = $eventClass | New-CimInstance -ClientOnly
    $eventTrigger.Enabled = $true
    $eventTrigger.Subscription = '<QueryList><Query Id="0" Path="Microsoft-Windows-NetworkProfile/Operational"><Select Path="Microsoft-Windows-NetworkProfile/Operational">*[System[Provider[@Name=''Microsoft-Windows-NetworkProfile''] and EventID=10000]]</Select></Query></QueryList>'

    $sessionClass = Get-CimClass -Namespace ROOT\Microsoft\Windows\TaskScheduler `
        -ClassName MSFT_TaskSessionStateChangeTrigger
    $unlockTrigger = New-CimInstance -CimClass $sessionClass `
        -Property @{ StateChange = 8; Enabled = $true } -ClientOnly

    # Omitting RepetitionDuration keeps this short-lived check scheduled indefinitely.
    $timerTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
        -RepetitionInterval (New-TimeSpan -Minutes 1)
    $principal = New-ScheduledTaskPrincipal -UserID "NT AUTHORITY\SYSTEM" `
        -LogonType ServiceAccount -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -RunOnlyIfNetworkAvailable `
        -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
        -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 3)
    $definition = New-ScheduledTask -Action $action `
        -Trigger @($eventTrigger, $unlockTrigger, $timerTrigger) `
        -Settings $settings -Principal $principal
    if ($Preview) {
        # Export a reviewable definition without registering or changing any task.
        [ordered]@{
            Action = $definition.Actions[0] | Select-Object Execute, Arguments, WorkingDirectory
            Principal = $definition.Principal | Select-Object UserId, LogonType, RunLevel
            Settings = $definition.Settings | Select-Object MultipleInstances, ExecutionTimeLimit,
                WakeToRun, RunOnlyIfNetworkAvailable, DisallowStartIfOnBatteries, StopIfGoingOnBatteries
            Triggers = @($definition.Triggers | ForEach-Object {
                [ordered]@{
                    ClassName = $_.CimClass.CimClassName
                    Enabled = $_.Enabled
                    Subscription = $_.Subscription
                    StateChange = $_.StateChange
                    StartBoundary = $_.StartBoundary
                    Interval = $_.Repetition.Interval
                    Duration = $_.Repetition.Duration
                }
            })
        } | ConvertTo-Json -Depth 5
        exit 0
    }
    Register-ScheduledTask -TaskName $TaskName -InputObject $definition -Force | Out-Null
    Write-Host "SUCCESS: Task registered with network, unlock, and one-minute triggers."
    exit 0
} catch {
    Write-Error "FAILURE: Scheduled task could not be prepared."
    exit 1
}
