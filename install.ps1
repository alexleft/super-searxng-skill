<#
.SYNOPSIS
    Installs (or updates) super-searxng-skill into the DSH skills directory.

.DESCRIPTION
    Copies SKILL.md, searxng.py, and searxng.ps1 into
    $env:USERPROFILE\.dsh\skills\searxng (or the directory given by -Target).
    Existing files are backed up to a .bak-<timestamp> sibling first.

    On non-Windows, use install.sh instead.

.PARAMETER Target
    Destination skills directory. Defaults to ~/.dsh/skills/searxng.

.PARAMETER NoBackup
    Skip the timestamped backup of existing files.

.EXAMPLE
    pwsh -File install.ps1
    pwsh -File install.ps1 -Target D:\dsh\skills\searxng
#>
[CmdletBinding()]
param(
    [string]$Target = (Join-Path $env:USERPROFILE ".dsh\skills\searxng"),
    [switch]$NoBackup
)

$ErrorActionPreference = "Stop"
$source = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "Installing super-searxng-skill"
Write-Host "  source: $source"
Write-Host "  target: $Target"

if (-not (Test-Path -LiteralPath $Target)) {
    New-Item -ItemType Directory -Path $Target -Force | Out-Null
    Write-Host "  created target directory"
}

$files = @("SKILL.md", "searxng.py", "searxng.ps1")
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"

foreach ($f in $files) {
    $src = Join-Path $source $f
    $dst = Join-Path $Target $f
    if (-not (Test-Path -LiteralPath $src)) {
        Write-Warning "source missing: $src"
        continue
    }
    if ((Test-Path -LiteralPath $dst) -and -not $NoBackup) {
        $bak = "$dst.bak-$stamp"
        Copy-Item -LiteralPath $dst -Destination $bak -Force
        Write-Host "  backed up $f -> $(Split-Path -Leaf $bak)"
    }
    Copy-Item -LiteralPath $src -Destination $dst -Force
    Write-Host "  installed $f"
}

Write-Host ""
Write-Host "Done. Restart or reload the DSH session to pick up the skill."
Write-Host "Quick test:"
Write-Host "  & `"$Target\searxng.ps1`" -Query `"hello`" -Limit 2"
