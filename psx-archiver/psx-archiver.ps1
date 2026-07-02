<#
.SYNOPSIS
    psx-archiver — cross-platform launcher (Windows).
.DESCRIPTION
    PlayStation disc image archiving pipeline: extraction (7z),
    conversion (CHD for PS1, CSO for PS2/PSP) then renaming via a serials database.
    Delegates to the Python package `psx_archiver`; all options are forwarded.
    No pip installation required: the script directory is added to PYTHONPATH.
.PARAMETER Args
    Options passed to the module, e.g. "--platform ps1 .\roms .\out".
.EXAMPLE
    .\psx-archiver.ps1 --platform ps1 .\roms .\out
.EXAMPLE
    .\psx-archiver.ps1 --platform ps2 --skip-extract --dry-run .\iso .\out
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

& $exe @prefix -m psx_archiver @args
exit $LASTEXITCODE
