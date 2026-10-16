# Disposable Windows CI only. The installed user application never invokes PowerShell.
param([string]$ArchiveFile, [string]$ManifestFile, [string]$OutputDirectory)
$ErrorActionPreference='Stop'
if ($env:GITHUB_ACTIONS -ne 'true') { throw 'Use a disposable hosted Windows runner.' }
& "$PSScriptRoot\build-installer.ps1"
$installer=Join-Path $PSScriptRoot 'Install Flapart.exe'
if (!$ArchiveFile -or !$ManifestFile) {
    $run=Start-Process -FilePath $installer -ArgumentList '--quiet' -Wait -PassThru
    if ($run.ExitCode -eq 0) { throw 'Unqualified candidate was not refused.' }
    python "$PSScriptRoot\smoke_installer.py"
    if ($LASTEXITCODE -ne 0) { throw 'Native synthetic installer mechanics failed.' }
    Write-Host 'Native Windows installer compile, refusal and synthetic mechanics passed. No painting runtime tested.'; exit 0
}
$work=Join-Path $env:RUNNER_TEMP ('flapart-installer-'+[Guid]::NewGuid().ToString('N')); New-Item -ItemType Directory -Path $work | Out-Null
try {
    $source=Join-Path $work 'source';New-Item -ItemType Directory -Path $source | Out-Null
    Copy-Item -LiteralPath $installer -Destination $source;Copy-Item -LiteralPath $ManifestFile -Destination (Join-Path $source 'release.json')
    $dest=Join-Path $work 'installed'
    # & in a script waits for GUI-native commands and passes each argument as data.
    & (Join-Path $source 'Install Flapart.exe') --quiet --archive $ArchiveFile --destination $dest --no-shortcut
    if ($LASTEXITCODE -ne 0) { throw 'Native install failed.' }
    $receipt=Join-Path $dest 'flapart-install.json';$before=(Get-FileHash $receipt).Hash
    $record=Get-Content $receipt -Raw | ConvertFrom-Json
    $bad=Join-Path $work 'corrupt.zip';[IO.File]::WriteAllText($bad,'deliberately invalid candidate')
    & (Join-Path $source 'Install Flapart.exe') --quiet --archive $bad --destination $dest --no-shortcut
    if ($LASTEXITCODE -eq 0 -or (Get-FileHash $receipt).Hash -ne $before) { throw 'Corrupt upgrade was not refused safely.' }
    New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
    @{ installer_passed=$true; corrupted_upgrade_refused=$true; active_receipt_preserved=$true; native_runtime_tested=$false; platform='Windows'; sha256=$record.sha256 } | ConvertTo-Json | Set-Content (Join-Path $OutputDirectory 'installer-result.json')
    Write-Host 'Native installer transaction passed. Use ci_e2e.py for actual launcher, artwork and preservation checks.'
} finally { Remove-Item -LiteralPath $work -Recurse -Force }
