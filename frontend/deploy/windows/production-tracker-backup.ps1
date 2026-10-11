# Daily backup of the production_tracker database, run by the "Production Tracker backup" scheduled task.
# Keeps $KeepDays days of compressed
# custom-format dumps; restore one with:
#   pg_restore -U postgres -d production_tracker --clean <file>
# The postgres password is read from $PassFile (PostgreSQL's pgpass format). A failure is
# written to the website's error log and to the task's result.
param(
    [string]$BackupDir = 'D:\ProductionTrackerBackups',
    [int]$KeepDays = 30,
    [string]$PassFile = 'C:\ProductionTracker\backup\pgpass.conf',
    [string]$LogFile = 'C:\ProductionTracker\app\logs\errors.log'
)

function Fail([string]$Message) {
    $offset = (Get-Date -Format 'zzz').Replace(':', '')
    $line = '{0} {1} ERROR [tracker.backup] {2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $offset, $Message
    [Console]::Error.WriteLine($line)
    try { [IO.File]::AppendAllText($LogFile, $line + [Environment]::NewLine) } catch { }
    exit 1
}

# The newest installed PostgreSQL's pg_dump.
$pgDump = Get-ChildItem 'C:\Program Files\PostgreSQL\*\bin\pg_dump.exe' -ErrorAction SilentlyContinue |
    Sort-Object { [int]$_.Directory.Parent.Name } | Select-Object -Last 1
if (-not $pgDump) { Fail 'pg_dump.exe not found under C:\Program Files\PostgreSQL' }

$date = Get-Date -Format 'yyyy-MM-dd'
$file = Join-Path $BackupDir "production_tracker-$date.dump"
try { New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null } catch { Fail "cannot create $BackupDir" }

$env:PGPASSFILE = $PassFile
& $pgDump.FullName -h localhost -U postgres -w -Fc -d production_tracker -f "$file.partial"
if ($LASTEXITCODE -ne 0) { Fail "pg_dump failed; no backup for $date" }
try { Move-Item -Force "$file.partial" $file } catch { Fail 'cannot move the finished backup into place' }

Get-ChildItem $BackupDir -Filter 'production_tracker-*.dump' |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$KeepDays) } |
    Remove-Item
