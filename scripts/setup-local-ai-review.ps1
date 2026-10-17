$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo
foreach ($cmd in @("ollama", "git", "npm", "python")) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
    throw "Required command '$cmd' was not found. Install it, reopen PowerShell, and rerun setup."
  }
}
$Tags = Invoke-RestMethod "http://localhost:11434/api/tags" -TimeoutSec 10
$Model = "gemma4:e2b"
if (-not ($Tags.models | Where-Object { $_.name -eq $Model -or $_.model -eq $Model })) {
  Write-Host "Downloading local vision model $Model (one-time download)..."
  ollama pull $Model
}
if (-not (Test-Path (Join-Path $Repo "node_modules"))) { npm install }
Write-Host "Setup complete. This installs the runner, but does not start an endless background task."
Write-Host "Run the loop manually: .\scripts\run-local-ai-review.ps1"
Write-Host "The loop runs up to 10 iterations, targets 8.5/10, and stops after 3 non-improving proposals."
