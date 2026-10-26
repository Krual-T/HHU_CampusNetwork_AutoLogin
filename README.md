# HHU Campus Network Auto Login

A short-lived Windows executable for the Hohai University captive portal. The scheduled
task starts it on network connection, workstation unlock, and once per minute. Each run
finishes after bounded work; the executable does not install a Windows service.

## Candidate status

This branch is a locally built, offline-tested candidate based on `293b24c`. The installed
executable and the registered `HohaiAutoLogin` task have not been replaced. The candidate
has not submitted a real login or logout. Complete the review and the controlled upgrade
below before treating it as deployed.

## Behavior

- Read the current Wi-Fi interface, SSID, and MAC together. A missing or ambiguous
  connected interface stops authentication. Recheck the complete identity immediately
  before each credential POST and before own-session logout.
- Probe the existing gateway and accept an online result only at the exact HTTP portal
  hosts (`10.96.0.155`, `eportal.hhu.edu.cn`) and `/eportal/success.jsp` path. Validate the
  portal index URL before extracting its dynamic query string. Known index page ports
  80 and 8080 are accepted; the API remains on port 80. Normalize URL dot-segments
  such as `/eportal/./success.jsp` before matching the exact endpoint path.
- Preserve the existing login endpoint, fields, and double URL encoding. Ignore
  environment proxies. Parse JSON responses and confirm authentication with up to three
  GET probes. A lost login response also gets read-only confirmation before a retry.
- Retry transient probes/login requests at most three times with one- and two-second
  pauses. Explicit rejection starts a persistent five-minute login cooldown and returns
  a nonzero exit code.
- Use a global Windows named mutex across SYSTEM and interactive sessions. The task
  definition also uses `IgnoreNew`. Another active instance causes a harmless exit.
- Log fixed status codes only. Credentials, identifiers, URL parameters, portal bodies,
  and exception details stay out of the logs. `DEBUG` remains a compatible configuration
  key; the windowed executable stays silent and never pauses for input.

## Own-session recovery

After a confirmed online probe, save the configured account, current Wi-Fi MAC, and the
single `userIndex` from `success.jsp`. Passwords are never saved in state.

Only JSON with `result=fail` and a `message` containing `limit_users_Err` enters recovery.
The saved account and MAC must match this machine. A read-only `getOnlineUserInfo` request
must then return `result=success` or `result=wait` and the same account, normalized MAC,
and `userIndex`. Recheck Wi-Fi after this lookup and after persisting the cooldown.

Persist a five-minute recovery cooldown **before** submitting logout, then POST only that
verified `userIndex`. A lost response keeps the cooldown. A confirmed logout permits one
new bounded authentication flow, followed by an online probe. Success preserves the
recovery cooldown. There is no whole-account logout or device enumeration.

An absent/expired old session, changed account/MAC, unconfirmed response, or network
change stops automatic logout. The next normal successful login can establish a new
saved session. Randomized Wi-Fi MAC changes may therefore require manual portal action.

## Configuration and state

Keep the existing five `.env` keys, or set the corresponding process environment:

```ini
PORTAL_USERNAME=your_account
PORTAL_PASSWORD=your_password
SERVICE_NAME=your_existing_service
TARGET_SSID="Hohai University"
DEBUG=False
```

The executable loads `.env` beside itself. Source execution loads `.env` from the project
root. Environment values take precedence. Empty credentials cause exit code 4; there
are no built-in credentials. The spec includes no `.env` or application state.

State is `%LOCALAPPDATA%\HohaiAutoLogin\session.json` for the **running account**.
The existing task runs as SYSTEM, whose usual location is
`C:\Windows\System32\config\systemprofile\AppData\Local\HohaiAutoLogin\session.json`.
An interactive run uses your own profile and has separate state. This means the first
SYSTEM run needs a confirmed normal session before it can recover a later terminal limit.
Identical saved state skips disk writes and ACL setup during minute checks.
Directory inheritance is removed with `icacls`, granting full control to the running
account and SYSTEM; the JSON file inherits those restricted permissions. ACL failure
stops persistence and prevents a recovery logout. Treat this file as private metadata.

`--check` performs only Wi-Fi inspection and GET probes. It needs no credentials, never
opens the mutex, and does not read or write application state:

```powershell
uv run --frozen python src\fast_login.py --check
$LASTEXITCODE
```

Exit codes: 0 online/success (also another instance or a normal run on another network),
1 unconfirmed operation, 2 check found offline/unavailable/another network, 4 missing
credentials, 5 explicit rejection or cooldown. The GUI executable reports through its
process exit code; run source for visible fixed status messages.

## Isolated Windows build and verification

Use Python 3.11+ and uv from the candidate worktree. No installed `.env` is required for
these offline tests. Dependencies are locked in `uv.lock`.

```powershell
uv sync --frozen --python 3.11
uv run --frozen ruff check src\configs.py src\fast_login.py tests
uv run --frozen ruff format --check src\configs.py src\fast_login.py tests
uv run --frozen pytest -q --cov=fast_login --cov=configs --cov-report=term-missing --cov-fail-under=80
uv run --frozen pyinstaller --noconfirm --clean --distpath dist\candidate --workpath build\candidate HohaiAutoLogin.spec
```

The reused windowed spec resolves the entry point and import path against `SPECPATH/src`,
so it packages this worktree's configuration module. Tests mock HTTP, use synthetic
identities, and include a real second Windows process for mutex exclusion. They never
disconnect Wi-Fi or call the real portal API. `dist`, `build`, `.venv`, `.env`, and state
stay ignored. The candidate executable is `dist\candidate\HohaiAutoLogin.exe`.

For a real read-only smoke check without copying the installed configuration:

```powershell
$check = Start-Process .\dist\candidate\HohaiAutoLogin.exe -ArgumentList '--check' -Wait -PassThru
$check.ExitCode
.\create_task.ps1 -TaskName HohaiAutoLogin -ExePath .\dist\candidate\HohaiAutoLogin.exe -Preview
```

`-Preview` builds a task definition in memory and prints JSON; it never registers a task.
The one-minute trigger has no repetition end date and does not wake a sleeping machine.
The task has a three-minute execution limit and retains SYSTEM/Highest privileges.

## Upgrade after review (administrator PowerShell)

Use the candidate worktree as the current directory. Keep the existing installation
directory and its `.env`; the following commands back up code and the current task only.
Wait for any currently running task instance to finish before proceeding.

```powershell
$ErrorActionPreference = 'Stop'
$install = 'C:\Program Files\HohaiAutoLogin'
$taskName = 'HohaiAutoLogin'
if ((Get-ScheduledTask -TaskName $taskName).State -eq 'Running') { throw 'Wait for the task to finish.' }
$backup = Join-Path $install ('backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $backup | Out-Null
Copy-Item -LiteralPath "$install\HohaiAutoLogin.exe" -Destination $backup
Export-ScheduledTask -TaskName $taskName | Set-Content -LiteralPath "$backup\task.xml" -Encoding Unicode
Disable-ScheduledTask -TaskName $taskName | Out-Null
if ((Get-ScheduledTask -TaskName $taskName).State -eq 'Running') { throw 'Task became active; wait before replacing.' }
Copy-Item -LiteralPath .\dist\candidate\HohaiAutoLogin.exe -Destination "$install\HohaiAutoLogin.exe"
.\create_task.ps1 -TaskName $taskName -ExePath "$install\HohaiAutoLogin.exe"
if ($LASTEXITCODE -ne 0) { throw "Task update failed. Restore from $backup." }
$check = Start-Process "$install\HohaiAutoLogin.exe" -ArgumentList '--check' -Wait -PassThru
$check.ExitCode
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State
```

The newly registered enabled task can run within one minute. Observe a normal connection
under the task's account, its exit result, and its private saved session before testing
a later terminal-limit event. A nonzero `--check` result means the read-only probe did
not confirm online access; it does not submit authentication.

## Rollback (administrator PowerShell)

Set `$backup` to the directory created above. Wait for the task to finish, disable it,
restore the old executable and exported task, then retain or remove the new state later
as appropriate. The previous executable ignores this candidate's state.

```powershell
$ErrorActionPreference = 'Stop'
$install = 'C:\Program Files\HohaiAutoLogin'
$taskName = 'HohaiAutoLogin'
$backup = 'C:\Program Files\HohaiAutoLogin\backup-YYYYMMDD-HHMMSS'
Disable-ScheduledTask -TaskName $taskName | Out-Null
if ((Get-ScheduledTask -TaskName $taskName).State -eq 'Running') { throw 'Wait for the task to finish.' }
Copy-Item -LiteralPath "$backup\HohaiAutoLogin.exe" -Destination "$install\HohaiAutoLogin.exe"
Register-ScheduledTask -TaskName $taskName -Xml (Get-Content -LiteralPath "$backup\task.xml" -Raw) -Force | Out-Null
```

The old `.env` stays in place throughout both procedures. Backups and private state must
remain outside Git. Login, logout, task registration, and installation replacement are
deliberately separate from the candidate's offline validation.
