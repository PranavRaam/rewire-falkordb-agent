param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $RewireArgs
)

$ErrorActionPreference = 'Stop'
$env:PYTHONPATH = Join-Path $PSScriptRoot 'src'
$dotenvPath = Join-Path $PSScriptRoot '.env'
if (Test-Path -LiteralPath $dotenvPath) {
    $allowedKeys = @(
        'REWIRE_FALKOR_HOST', 'REWIRE_FALKOR_PORT',
        'REWIRE_FALKOR_USERNAME', 'REWIRE_FALKOR_PASSWORD', 'REWIRE_SCENARIO',
        'OPENAI_API_KEY', 'REWIRE_LLM_API_KEY', 'REWIRE_LLM_PROVIDER',
        'REWIRE_LLM_MODEL', 'REWIRE_LLM_BASE_URL', 'REWIRE_LLM_CONTEXT',
        'REWIRE_LLM_MAX_TOKENS', 'REWIRE_LLM_TIMEOUT_SECONDS'
    )
    foreach ($line in Get-Content -LiteralPath $dotenvPath) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#') -or -not $trimmed.Contains('=')) { continue }
        $key, $value = $trimmed.Split('=', 2)
        $key = $key.Trim()
        if ($allowedKeys -contains $key) {
            Set-Item -Path ("Env:$key") -Value $value.Trim()
        }
    }
}
$pythonCommand = (Get-Command python -ErrorAction Stop).Source
$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $venvPython) {
    & $venvPython -c 'import falkordb; import mcp' 2>$null
    if ($LASTEXITCODE -eq 0) { $pythonCommand = $venvPython }
}
& $pythonCommand -m rewire.cli @RewireArgs
exit $LASTEXITCODE
