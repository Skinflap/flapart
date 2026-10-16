# Build-time only; Windows users receive the compiled EXE and need no PowerShell.
param([string]$OutputDirectory = $PSScriptRoot)
$ErrorActionPreference='Stop'
$csc=Join-Path ([Runtime.InteropServices.RuntimeEnvironment]::GetRuntimeDirectory()) 'csc.exe'
if (!(Test-Path $csc)) { $csc=Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe' }
if (!(Test-Path $csc)) { throw 'Windows .NET Framework C# compiler not found on build runner.' }
New-Item -ItemType Directory -Force $OutputDirectory | Out-Null
& $csc /nologo /target:winexe /platform:anycpu /optimize+ /out:"$OutputDirectory\Install Flapart.exe" /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.Web.Extensions.dll /reference:System.IO.Compression.dll "$PSScriptRoot\FlapartInstaller.cs"
if ($LASTEXITCODE -ne 0) { throw 'Native installer compilation failed.' }
Write-Host 'Compiled native installer/launcher. User execution requires .NET Framework, not PowerShell policy changes.'
