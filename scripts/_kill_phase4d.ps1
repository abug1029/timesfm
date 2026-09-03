# Phase 4d 进程精准树杀 (避开 tail/.log, 防御 venv 双进程 + 伪停止)
$ErrorActionPreference = "SilentlyContinue"

$filter = {
    ($_.Name -match "python" -and $_.CommandLine -match "monthly_backtest\.py") -or
    ($_.Name -match "bash" -and $_.CommandLine -match "phase4d_calendar_matrix\.sh" -and $_.CommandLine -notmatch "bash -c")
}

$procs = Get-CimInstance Win32_Process | Where-Object $filter

if (-not $procs) {
    Write-Output "NONE FOUND - clean"
} else {
    foreach ($p in $procs) {
        $cmd = if ($p.CommandLine) { $p.CommandLine.Substring(0, [Math]::Min(55, $p.CommandLine.Length)) } else { "(no cmd)" }
        # /T 树杀: 连带 bash 衍生的子 python (venv launcher + SDK python)
        taskkill /F /T /PID $p.ProcessId | Out-Null
        Write-Output "killed PID $($p.ProcessId) [$($p.Name)] $cmd"
    }
    Start-Sleep -Milliseconds 600
    $remain = Get-CimInstance Win32_Process | Where-Object $filter
    if ($remain) {
        Write-Output "STILL ALIVE:"
        $remain | ForEach-Object { Write-Output "  PID $($_.ProcessId) [$($_.Name)]" }
    } else {
        Write-Output "VERIFIED CLEAN"
    }
}
