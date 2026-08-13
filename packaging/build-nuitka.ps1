param([string]$Python = "python")
$ErrorActionPreference = 'Stop'
& $Python -m nuitka --standalone --enable-plugin=pyside6 --windows-console-mode=disable --include-data-dir=app/ui/assets=app/ui/assets --output-dir=dist app/main.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Copy-Item -Recurse -Force config,models dist/main.dist/
New-Item -ItemType Directory -Path (Join-Path 'dist/main.dist' 'state') -Force | Out-Null
