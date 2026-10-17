param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $SimulatorArgs
)

$ErrorActionPreference = 'Stop'
$env:PYTHONPATH = Join-Path $PSScriptRoot 'services\simulator'
$pythonCommand = (Get-Command python -ErrorAction Stop).Source
$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $venvPython) {
    & $venvPython -c 'import rewire_simulator' 2>$null
    if ($LASTEXITCODE -eq 0) { $pythonCommand = $venvPython }
}
& $pythonCommand -m rewire_simulator @SimulatorArgs
exit $LASTEXITCODE
