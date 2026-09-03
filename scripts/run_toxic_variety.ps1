$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"
$job = Start-Process -FilePath "D:\FlyBuddy\shared\timesfm\.venv\Scripts\python.exe" `
    -ArgumentList "scripts\toxic_variety_runner.py" `
    -WorkingDirectory "D:\FlyBuddy\FM_a" `
    -NoNewWindow -RedirectStandardOutput "reports\toxic_variety_stdout.log" `
    -RedirectStandardError "reports\toxic_variety_stderr.log" -PassThru
"全量回测已启动, PID: $($job.Id)"
$job.Id | Out-File -FilePath "reports\.toxic_variety.pid" -NoNewline
