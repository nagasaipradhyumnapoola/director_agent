param(
    [switch]$RemoveVenv
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $root
try {
    $python = Join-Path $root ".venv\Scripts\python.exe"
    if (Test-Path $python) {
        $site = (& $python -c "import site; print(site.getsitepackages()[0])").Trim()
        Remove-Item -LiteralPath (Join-Path $site "director-src.pth") -Force -ErrorAction SilentlyContinue
    }
    if ($RemoveVenv -and (Test-Path (Join-Path $root ".venv"))) {
        Write-Host "Removing .venv"
        Remove-Item -LiteralPath (Join-Path $root ".venv") -Recurse -Force
    }
    Write-Host "Uninstalled the local source-path entry."
    Write-Host "Project state under .director/, research files and generated adapters were NOT deleted."
}
finally {
    Pop-Location
}
