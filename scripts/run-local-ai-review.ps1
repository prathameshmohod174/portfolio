$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
Set-Location $Repo
try { Invoke-RestMethod "http://localhost:11434/api/tags" -TimeoutSec 5 | Out-Null }
catch { throw "Ollama is not responding. Start Ollama and retry." }
if (-not $env:OLLAMA_MODEL) { $env:OLLAMA_MODEL = "gemma4:e2b" }
if (-not $env:VISUAL_TARGET) { $env:VISUAL_TARGET = "8.5" }
if (-not $env:VISUAL_MAX_ITERATIONS) { $env:VISUAL_MAX_ITERATIONS = "10" }
python (Join-Path $Repo "scripts\local_ollama_visual_loop.py")
if ($LASTEXITCODE -ne 0) { throw "Visual loop failed; unvalidated changes were not pushed." }
