$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
& "$PSScriptRoot/.venv/Scripts/python.exe" -m uvicorn backend.api:app --host 127.0.0.1 --port 8770
