param(
    [ValidateSet('legacy', 'cpu', 'vulkan', 'cuda')]
    [string]$Variant = 'legacy'
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$SpeechRoot = Join-Path $ProjectRoot 'app_data\speech\crispasr'
$Runtime = Join-Path $SpeechRoot 'runtime'
$Staging = Join-Path $SpeechRoot ('.install-' + [Guid]::NewGuid().ToString('N'))
$Archive = Join-Path $Staging 'crispasr.zip'

function Select-CrispAsset($Assets, [string]$RequestedVariant) {
    $Patterns = switch ($RequestedVariant) {
        'legacy' { @('*windows*x86_64*cpu-legacy*.zip', '*windows*x86_64*legacy*.zip', '*windows*x86_64*cpu*.zip') }
        'cpu'    { @('*windows*x86_64*cpu.zip', '*windows*x86_64*.zip') }
        'vulkan' { @('*windows*x86_64*vulkan*.zip') }
        'cuda'   { @('*windows*x86_64*cuda*.zip') }
    }
    foreach ($Pattern in $Patterns) {
        $Match = $Assets | Where-Object {
            $_.name -like $Pattern -and $_.name -notlike 'libcrispasr*'
        } | Select-Object -First 1
        if ($null -ne $Match) { return $Match }
    }
    return $null
}

try {
    New-Item -ItemType Directory -Force -Path $Staging | Out-Null
    Write-Host '[1/4] Ermittle die aktuelle CrispASR-Windows-Version ...'
    $Headers = @{ 'User-Agent' = 'OllamaVibeDesk-installer'; 'Accept' = 'application/vnd.github+json' }
    $Release = Invoke-RestMethod -Headers $Headers -Uri 'https://api.github.com/repos/CrispStrobe/CrispASR/releases/latest'
    $Asset = Select-CrispAsset $Release.assets $Variant
    if ($null -eq $Asset) {
        throw "Kein passendes Windows-$Variant-Archiv im aktuellen CrispASR-Release gefunden."
    }

    Write-Host ("[2/4] Lade {0} ..." -f $Asset.name)
    Invoke-WebRequest -Headers $Headers -Uri $Asset.browser_download_url -OutFile $Archive
    if ((Get-Item $Archive).Length -lt 1MB) { throw 'Der Download ist unerwartet klein.' }

    $Extracted = Join-Path $Staging 'extracted'
    Write-Host '[3/4] Entpacke und pruefe die Laufzeit ...'
    Expand-Archive -LiteralPath $Archive -DestinationPath $Extracted -Force
    $Executable = Get-ChildItem -LiteralPath $Extracted -Filter 'crispasr.exe' -File -Recurse | Select-Object -First 1
    if ($null -eq $Executable) { throw 'crispasr.exe fehlt im heruntergeladenen Archiv.' }
    & $Executable.FullName --help *> $null
    if ($LASTEXITCODE -ne 0) { throw "crispasr.exe konnte nicht gestartet werden (Code $LASTEXITCODE)." }

    $NewRuntime = Join-Path $SpeechRoot '.runtime-new'
    $Backup = Join-Path $SpeechRoot '.runtime-backup'
    if (Test-Path -LiteralPath $NewRuntime) { Remove-Item -LiteralPath $NewRuntime -Recurse -Force }
    # Keep the entire release layout. Some variants place runtime DLLs or data
    # beside a nested bin directory rather than directly beside the executable.
    Move-Item -LiteralPath $Extracted -Destination $NewRuntime
    if (Test-Path -LiteralPath $Backup) { Remove-Item -LiteralPath $Backup -Recurse -Force }
    if (Test-Path -LiteralPath $Runtime) { Move-Item -LiteralPath $Runtime -Destination $Backup }
    Move-Item -LiteralPath $NewRuntime -Destination $Runtime
    if (Test-Path -LiteralPath $Backup) { Remove-Item -LiteralPath $Backup -Recurse -Force }

    Write-Host '[4/4] CrispASR wurde erfolgreich installiert.' -ForegroundColor Green
    Write-Host 'Die ausgewaehlten Modelle werden beim ersten Einsatz aus dem offiziellen Runtime-Katalog geladen.'
}
finally {
    if (Test-Path -LiteralPath $Staging) { Remove-Item -LiteralPath $Staging -Recurse -Force }
}
