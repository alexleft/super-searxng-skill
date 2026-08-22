<#
.SYNOPSIS
    Windows launcher for super-searxng-skill. Resolves a Python interpreter
    and forwards arguments to searxng.py. All HTTP/TLS/concurrency/JSON/
    Markdown live in Python so PowerShell language mode (FullLanguage vs
    ConstrainedLanguage) is irrelevant.

.DESCRIPTION
    Two invocation styles:

      1. Named parameters (recommended, reliable binding):
           & searxng.ps1 -Query "deepseek v3" -Language en
           & searxng.ps1 -Queries "a","b","c" -Merge -Limit 8

      2. Raw pass-through (everything after -- goes to python verbatim):
           & searxng.ps1 -- "deepseek v3" --language en
           & searxng.ps1 -- --queries a b c --merge

    Pipeline input is accepted and piped to python's stdin. Add -Stdin to
    tell python to parse it as a JSON request.

    Python resolution: $env:SEARXNG_PYTHON -> python.exe -> py.exe -> python3.exe
    (on Unix, invoked through pwsh: python3 -> python).
#>
[CmdletBinding(DefaultParameterSetName = "Named")]
param(
    [Parameter(ParameterSetName = "Named")]
    [string]$Query,

    [Parameter(ParameterSetName = "Named")]
    [string[]]$Queries,

    [Parameter(ParameterSetName = "Named")]
    [string]$Category = "",

    [Parameter(ParameterSetName = "Named")]
    [string]$Language = "",

    [Parameter(ParameterSetName = "Named")]
    [int]$Page = 0,

    [Parameter(ParameterSetName = "Named")]
    [string]$TimeRange = "",

    [Parameter(ParameterSetName = "Named")]
    [int]$SafeSearch = -1,

    [Parameter(ParameterSetName = "Named")]
    [string]$Engines = "",

    [Parameter(ParameterSetName = "Named")]
    [int]$Limit = -1,

    [Parameter(ParameterSetName = "Named")]
    [switch]$Merge,

    [Parameter(ParameterSetName = "Named")]
    [int]$MaxConcurrency = -1,

    [Parameter(ParameterSetName = "Named")]
    [int]$Timeout = -1,

    [Parameter(ParameterSetName = "Named")]
    [string]$BaseUrl = "",

    [Parameter(ParameterSetName = "Named")]
    [string]$FallbackEngines = "",

    [Parameter(ParameterSetName = "Named")]
    [switch]$NoFallbackEngines,

    [Parameter(ParameterSetName = "Named")]
    [switch]$Raw,

    [Parameter(ParameterSetName = "Named")]
    [switch]$Stdin,

    [Parameter(ParameterSetName = "Passthrough", ValueFromRemainingArguments = $true)]
    $PassthroughArgs,

    [Parameter(ValueFromPipeline = $true)]
    $PipelineInput
)
begin {
    $pipelineBuffer = @()
}
process {
    if ($null -ne $PipelineInput) {
        foreach ($item in @($PipelineInput)) {
            $pipelineBuffer += [string]$item
        }
    }
}
end {
    $ErrorActionPreference = "Stop"
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $pyScript = Join-Path $scriptDir "searxng.py"
    if (-not (Test-Path -LiteralPath $pyScript)) {
        throw "searxng.py not found next to searxng.ps1 (looked in $scriptDir)"
    }

    # Resolve Python interpreter.
    $python = $env:SEARXNG_PYTHON
    if (-not $python) {
        $isWin = ($env:OS -eq "Windows_NT") -or ($null -ne $env:SystemRoot)
        if ($isWin) {
            $candidates = @("python.exe", "py.exe", "python3.exe")
        } else {
            $candidates = @("python3", "python")
        }
        foreach ($c in $candidates) {
            $cmd = Get-Command $c -ErrorAction SilentlyContinue
            if ($cmd) { $python = $cmd.Source; break }
        }
    }
    if (-not $python) {
        throw "No Python interpreter found. Install Python 3 or set SEARXNG_PYTHON."
    }

    # Build argv for python.
    if ($PSCmdlet.ParameterSetName -eq "Passthrough") {
        $argv = @($PassthroughArgs | ForEach-Object { [string]$_ })
    } else {
        $argv = @()
        if ($Queries -and $Queries.Count -gt 0) {
            $argv += "--queries"
            foreach ($q in $Queries) { $argv += [string]$q }
        } elseif ($Query) {
            $argv += [string]$Query
        }
        if ($Category)             { $argv += @("--category", $Category) }
        if ($Language)             { $argv += @("--language", $Language) }
        if ($Page -gt 0)           { $argv += @("--page", [string]$Page) }
        if ($TimeRange)            { $argv += @("--time-range", $TimeRange) }
        if ($SafeSearch -ge 0)     { $argv += @("--safesearch", [string]$SafeSearch) }
        if ($Engines)              { $argv += @("--engines", $Engines) }
        if ($Limit -ge 0)          { $argv += @("--limit", [string]$Limit) }
        if ($Merge)                { $argv += "--merge" }
        if ($MaxConcurrency -gt 0) { $argv += @("--max-concurrency", [string]$MaxConcurrency) }
        if ($Timeout -gt 0)        { $argv += @("--timeout", [string]$Timeout) }
        if ($BaseUrl)              { $argv += @("--base-url", $BaseUrl) }
        if ($FallbackEngines)      { $argv += @("--fallback-engines", $FallbackEngines) }
        if ($NoFallbackEngines)    { $argv += "--no-fallback-engines" }
        if ($Raw)                  { $argv += "--raw" }
        if ($Stdin)                { $argv += "--stdin" }
    }

    if ($pipelineBuffer.Count -gt 0) {
        $pipelineData = [string]::Join("`n", $pipelineBuffer)
        if ($pipelineData) {
            $pipelineData | & $python $pyScript @argv
            return
        }
    }

    & $python $pyScript @argv
}
