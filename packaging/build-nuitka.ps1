param([string]$Python = "python")
$ErrorActionPreference = 'Stop'
& $Python -m nuitka --standalone --enable-plugin=pyside6 --windows-console-mode=disable --include-data-dir=app/ui/assets=app/ui/assets --output-dir=dist app/main.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Copy-Item -Recurse -Force config,models dist/main.dist/
New-Item -ItemType Directory -Path (Join-Path 'dist/main.dist' 'state') -Force | Out-Null
$serverSource = Join-Path 'runtime' 'llama-server'
if (Test-Path -LiteralPath $serverSource -PathType Container) {
    $serverDestination = Join-Path 'dist/main.dist' 'runtime\llama-server'
    New-Item -ItemType Directory -Path $serverDestination -Force | Out-Null
    Copy-Item -Path (Join-Path $serverSource '*') -Destination $serverDestination -Recurse -Force
    $cudaBin = Join-Path 'runtime' 'python\Lib\site-packages\nvidia\cu13\bin\x86_64'
    if (Test-Path -LiteralPath $cudaBin -PathType Container) {
        Get-ChildItem -LiteralPath $cudaBin -File -Filter '*.dll' |
            Copy-Item -Destination $serverDestination -Force
    }
}
