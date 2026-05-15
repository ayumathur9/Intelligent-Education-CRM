# Registers a Windows Task Scheduler job that runs every Monday at 09:00.
# Run this script once as Administrator to set up the schedule.

$taskName  = "IntelligentEdu-ProfileReminders"
$projectDir = "d:\Intelligent Education\tool\CRMcursor\backend"
$python     = (Get-Command python -ErrorAction SilentlyContinue)?.Source
if (-not $python) { $python = "python" }

$action = New-ScheduledTaskAction `
    -Execute $python `
    -Argument "manage.py send_profile_reminders" `
    -WorkingDirectory $projectDir

# Every Monday at 09:00
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At "09:00"

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 5)

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -RunLevel Highest `
    -Force

Write-Host "Task '$taskName' registered. It will run every Monday at 09:00."
Write-Host "To run immediately: Start-ScheduledTask -TaskName '$taskName'"
Write-Host "To remove:         Unregister-ScheduledTask -TaskName '$taskName' -Confirm:`$false"
