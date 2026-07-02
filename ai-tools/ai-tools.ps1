<#
.SYNOPSIS
    ai-tools — cross-platform launcher (Windows).
.DESCRIPTION
    Delegates to the `ai_tools` Python package. All options are passed through as-is.
    No pip install required: the script's folder is added to PYTHONPATH.

    Commands:
      claude-export   Export local Claude Code/Desktop data into a ZIP
      img-resize      Resize and compress images (PNG/JPEG/WebP)
.PARAMETER Args
    Subcommand and options passed to the module (e.g. "claude-export --dry-run").
.EXAMPLE
    .\ai-tools.ps1 claude-export --dry-run
.EXAMPLE
    .\ai-tools.ps1 img-resize .\photos --max-dim 1920 -o .\out
#>
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Python detection: first `python`, otherwise the `py -3` launcher.
$exe = $null
$prefix = @()
if (Get-Command python -ErrorAction SilentlyContinue) {
    $exe = "python"
}
elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $exe = "py"; $prefix = @("-3")
}
else {
    Write-Error "Python not found (install Python 3, or the 'py' launcher)."
    exit 1
}

$sep = [IO.Path]::PathSeparator
$env:PYTHONPATH = "$scriptDir$sep$($env:PYTHONPATH)"

& $exe @prefix -m ai_tools @args
exit $LASTEXITCODE
