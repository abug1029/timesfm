# 杀手脚本 — 精准终止协变量空白补测的全部工作进程
# 匹配: monthly_backtest.py (python) + batch_X_cov_gap.sh (bash)
$processes = Get-CimInstance Win32_Process | Where-Object {
    ($_.CommandLine -match "monthly_backtest\.py" -and $_.Name -match "python") -or
    ($_.CommandLine -match "batch_[a-e]_cov_gap\.sh" -and $_.Name -match "bash")
}
if ($processes) {
    foreach ($p in $processes) {
        $cmdLine = if ($p.CommandLine.Length -gt 80) { $p.CommandLine.Substring(0, 80) } else { $p.CommandLine }
        Write-Host "Killing PID $($p.ProcessId): $cmdLine"
        taskkill /F /T /PID $p.ProcessId | Out-Null
    }
    Write-Host "Killed $($processes.Count) processes"
} else {
    Write-Host "No matching processes found"
}
