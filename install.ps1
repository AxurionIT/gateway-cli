param([switch]$Offline, [switch]$NoSetup)
$ErrorActionPreference = 'Stop'
$Version = '1.2.0-beta.5'
$Base = "https://github.com/AxurionIT/gateway-cli/releases/download/v$Version"
$PythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($PythonCommand) { $Python = $PythonCommand.Source; $Prefix = @() }
else { $Python = (Get-Command py -ErrorAction Stop).Source; $Prefix = @('-3') }
& $Python @Prefix -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else "Python 3.11+ required")'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ necessário.' }
$Temp = Join-Path ([IO.Path]::GetTempPath()) ('axurion-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $Temp | Out-Null
try {
    $Package = if ($PSScriptRoot) { Join-Path $PSScriptRoot 'dist/gateway-cli.pyz' } else { $null }
    if ($Package -and (Test-Path $Package)) { }
    elseif ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot 'scripts/build.py'))) {
        & $Python @Prefix (Join-Path $PSScriptRoot 'scripts/build.py')
        if ($LASTEXITCODE -ne 0) { throw 'Falha no build.' }
    } else {
        $Package = Join-Path $Temp 'gateway-cli.pyz'
        $Checksum = Join-Path $Temp 'gateway-cli.pyz.sha256'
        Write-Host "Baixando Axurion Gateway CLI v$Version..."
        foreach ($Asset in @('gateway-cli.pyz', 'gateway-cli.pyz.sha256')) {
            & curl.exe --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --connect-timeout 15 --max-time 120 "$Base/$Asset" -o (Join-Path $Temp $Asset)
            if ($LASTEXITCODE -ne 0) { throw "Falha no download: $Asset" }
        }
        $Expected = ((Get-Content -Raw $Checksum).Trim() -split '\s+')[0]
        $Actual = (Get-FileHash -Algorithm SHA256 $Package).Hash
        if ($Expected -notmatch '^[a-fA-F0-9]{64}$' -or $Actual -ne $Expected) { throw 'SHA-256 inválido: instalação interrompida.' }
        Write-Host 'SHA-256 verificado.'
    }
    if (-not $Offline) {
        $Venv = Join-Path $env:LOCALAPPDATA 'AxurionCliRuntime/venv'
        & $Python @Prefix -m venv $Venv
        if ($LASTEXITCODE -ne 0) { throw 'Falha na criação do ambiente Python.' }
        $Python = Join-Path $Venv 'Scripts/python.exe'
        $Prefix = @()
        & $Python -m pip install 'keyring>=25,<26'
        if ($LASTEXITCODE -ne 0) { Write-Warning 'Keyring indisponível; será oferecida uma alternativa local.' }
    }
    $InstallArgs = @('install')
    if (-not $NoSetup) { $InstallArgs += '--setup' }
    & $Python @Prefix $Package @InstallArgs
    if ($LASTEXITCODE -ne 0) { throw 'Falha na instalação ou configuração.' }
} finally {
    Remove-Item -LiteralPath $Temp -Recurse -Force -ErrorAction SilentlyContinue
}
