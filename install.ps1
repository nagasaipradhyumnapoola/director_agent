param(
    [switch]$NoVenv
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $root
try {
    $python = (Get-Command python -ErrorAction Stop).Source
    if (-not $NoVenv) {
        if (-not (Test-Path ".venv")) {
            & $python -m venv .venv
        }
        $python = Join-Path $root ".venv\Scripts\python.exe"
        $site = (& $python -c "import site; print(site.getsitepackages()[0])").Trim()
        $pth = Join-Path $site "director-src.pth"
        Set-Content -LiteralPath $pth -Value (Join-Path $root "src") -Encoding ascii
        Write-Host "Installed source path into $pth (offline; no global changes)."
    }
    else {
        $env:PYTHONPATH = (Join-Path $root "src") + ";" + $env:PYTHONPATH
        Write-Host "No venv created; PYTHONPATH is set for this session only."
    }

    & $python -m director --version
    if ($LASTEXITCODE -ne 0) {
        throw "DIRECTOR did not start."
    }
    Write-Host ""
    Write-Host "Next: python -m director init --root . --name my-project --domain general"
    Write-Host "Then: python -m director doctor"
    Write-Host "Tests (optional, needs pytest): python -m pytest"
}
finally {
    Pop-Location
}
