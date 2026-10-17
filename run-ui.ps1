param([int]$Port = 8787)
$ErrorActionPreference = 'Stop'
$env:PYTHONPATH = Join-Path $PSScriptRoot 'src'
$dotenvPath = Join-Path $PSScriptRoot '.env'
if (Test-Path -LiteralPath $dotenvPath) {
    foreach ($line in Get-Content -LiteralPath $dotenvPath) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#') -or -not $trimmed.Contains('=')) { continue }
        $key, $value = $trimmed.Split('=', 2)
        if ($key.Trim() -match '^(REWIRE_FALKOR_(HOST|PORT|USERNAME|PASSWORD)|REWIRE_LLM_(PROVIDER|MODEL|BASE_URL|API_KEY|CONTEXT|MAX_TOKENS|TIMEOUT_SECONDS)|OPENAI_API_KEY)$') {
            Set-Item -Path ("Env:" + $key.Trim()) -Value $value.Trim()
        }
    }
}
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Create .venv and install requirements.lock first.' }
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'apps\web\dist\index.html'))) {
    throw 'Build the UI first: cd apps/web; npm ci; npm run build'
}
Write-Host "Rewire control room: http://127.0.0.1:$Port"
Write-Host 'Keep FalkorDB and Ollama running. Ctrl+C stops the control room.'
& $pythonPath -m uvicorn rewire.web:app --host 127.0.0.1 --port $Port --workers 1
exit $LASTEXITCODE
