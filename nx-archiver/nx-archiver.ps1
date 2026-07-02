<#
.SYNOPSIS
    nx-archiver — cross-platform launcher (Windows).
.DESCRIPTION
    Tools for manipulating Nintendo Switch containers (XCI / NSP / NSZ).
    Delegates to the Python package `nx_archiver`; all options are forwarded.
    No pip install required: the script's folder is added to PYTHONPATH.

    Commands:
      make-xci      Builds one XCI per game from a folder of NSP/NSZ files
      nsp-to-xci    Converts one or more NSP/NSZ files into a single XCI
      xci-extract   Extracts the NCAs from an XCI
      xci-modify    Adds/removes NCAs in an XCI
      xci-update    Replaces the update NCAs of an XCI with a new update
      xci-trim      Removes the 0xFF padding from an XCI (lossless trim)

    The Switch keys are read from $env:NX_KEYS_DIR (default: ~/.switch/prod.keys).
.PARAMETER Args
    Subcommand and options passed to the module.
.EXAMPLE
    .\nx-archiver.ps1 make-xci .\nsp --dry-run
.EXAMPLE
    .\nx-archiver.ps1 xci-extract game.xci -o out
#>
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Python detection: `python` first, otherwise the `py -3` launcher.
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

& $exe @prefix -m nx_archiver @args
exit $LASTEXITCODE
