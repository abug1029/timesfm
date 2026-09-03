# _kill_batch.ps1 -- kill all batch_f[1-4] + monthly_backtest processes
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/_kill_batch.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/_kill_batch.ps1 -DryRun
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/_kill_batch.ps1 -ExcludePid 12345
param(
    [switch]$DryRun,
    [int]$ExcludePid = 0
)
$ErrorActionPreference = "SilentlyContinue"

$filter = {
    (($_.Name -match "bash") -and ($_.CommandLine -match "batch_f[1-4][a-c]?_single_cov") -and ($_.CommandLine -notmatch "bash -c")) -or
    (($_.Name -match "python") -and ($_.CommandLine -match "monthly_backtest"))
}

# 初始过滤仅排除直接匹配 (descendants 由 $protectedPids 统一管理)
$procs = Get-CimInstance Win32_Process | Where-Object $filter

# -- 自身批次保护: 排除 ExcludePid 自身 + 其所有后代进程 --
# matched 进程中, 属于当前批次链条的是 ExcludePid 的后代 (child → grandchild → ...)
# 需要收敛循环: 单次扫描可能因进程列表顺序遗漏中间层.
$protectedPids = @{}
if ($ExcludePid -gt 0) {
    $protectedPids[$ExcludePid] = $true
    $allProcs = Get-CimInstance Win32_Process
    for ($iter = 0; $iter -lt 10; $iter++) {
        $added = 0
        foreach ($p in $allProcs) {
            $ppid = $p.ParentProcessId
            if ($ppid -and $protectedPids.ContainsKey($ppid) -and -not $protectedPids.ContainsKey($p.ProcessId)) {
                $protectedPids[$p.ProcessId] = $true
                $added++
            }
        }
        if ($added -eq 0) { break }
    }
}

if ($protectedPids.Count -gt 0) {
    $procs = $procs | Where-Object { -not $protectedPids.ContainsKey($_.ProcessId) }
}

if (-not $procs) {
    Write-Output "NONE FOUND - clean"
    exit 0
}

$mode = if ($DryRun) { "[DRY-RUN]" } else { "[KILL]" }
Write-Output "Found matching processes:"

foreach ($p in $procs) {
    $cmd = if ($p.CommandLine) { $p.CommandLine.Substring(0, [Math]::Min(80, $p.CommandLine.Length)) } else { "(no cmd)" }
    $ppid = if ($p.ParentProcessId) { $p.ParentProcessId } else { "?" }
    Write-Output "  $mode PID $($p.ProcessId) [ppid=$ppid] [$($p.Name)] $cmd"
}

if ($DryRun) {
    Write-Output "DRY-RUN: no processes killed. Remove -DryRun to execute."
    exit 0
}

foreach ($p in $procs) {
    taskkill /F /PID $p.ProcessId 2>$null | Out-Null
    Write-Output "  killed PID $($p.ProcessId)"
}

Start-Sleep -Seconds 3

$remain = Get-CimInstance Win32_Process | Where-Object $filter
if ($protectedPids.Count -gt 0) {
    $remain = $remain | Where-Object { -not $protectedPids.ContainsKey($_.ProcessId) }
}
if ($remain) {
    Write-Output "WARNING: STILL ALIVE after kill:"
    $remain | ForEach-Object { Write-Output "  PID $($_.ProcessId) [$($_.Name)]" }
    exit 1
} else {
    Write-Output "VERIFIED CLEAN"
    $lockFile = Join-Path (Split-Path -Parent $PSScriptRoot) "reports\data_ops\.batch_runner.lock"
    $workerPidFile = Join-Path (Split-Path -Parent $PSScriptRoot) "reports\data_ops\.worker.pid"
    if (Test-Path $lockFile) { Remove-Item $lockFile -Force; Write-Output "  cleaned lock file" }
    if (Test-Path $workerPidFile) { Remove-Item $workerPidFile -Force; Write-Output "  cleaned worker.pid file" }
    exit 0
}
