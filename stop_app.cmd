@echo off
rem ClaimGuard-KR: stop the app running on port 8501.
set PORT=8501
powershell -NoProfile -Command "$ids = Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique; if ($ids) { $ids | ForEach-Object { Stop-Process -Id $_ -Force }; Write-Output 'Stopped ClaimGuard-KR.' } else { Write-Output 'ClaimGuard-KR is not running.' }"
