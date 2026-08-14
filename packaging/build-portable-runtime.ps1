param(
    [ValidateSet("cuda", "cpu")]
    [string]$Backend = "cuda"
)

$ErrorActionPreference = "Stop"
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$runtimeRoot = Join-Path $projectRoot "runtime"
$pythonRoot = Join-Path $runtimeRoot "python"
$downloadsRoot = Join-Path $runtimeRoot "downloads"
$pythonArchive = Join-Path $downloadsRoot "python-3.12.10-embed-amd64.zip"
$getPip = Join-Path $downloadsRoot "get-pip.py"
$pythonUrl = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
$pythonSha256 = "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3"

if (Test-Path -LiteralPath $pythonRoot) {
    throw "A portable runtime already exists at $pythonRoot. It was not changed."
}

New-Item -ItemType Directory -Path $pythonRoot -Force | Out-Null
New-Item -ItemType Directory -Path $downloadsRoot -Force | Out-Null
$env:PIP_CACHE_DIR = Join-Path $downloadsRoot "pip-cache"

Write-Host "Downloading official Python 3.12.10 embeddable runtime..."
Invoke-WebRequest -Uri $pythonUrl -OutFile $pythonArchive -UseBasicParsing
$actualHash = (Get-FileHash -LiteralPath $pythonArchive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $pythonSha256) {
    throw "The Python archive checksum did not match the official CPython release metadata."
}

Expand-Archive -LiteralPath $pythonArchive -DestinationPath $pythonRoot
New-Item -ItemType Directory -Path (Join-Path $pythonRoot "Lib\site-packages") -Force | Out-Null

$pathConfiguration = @(
    "python312.zip"
    "."
    "Lib\site-packages"
    "..\.."
    "import site"
) -join [Environment]::NewLine
Set-Content -LiteralPath (Join-Path $pythonRoot "python312._pth") -Value $pathConfiguration -Encoding ASCII

Write-Host "Installing pip into the application-local runtime..."
Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip -UseBasicParsing
$portablePython = Join-Path $pythonRoot "python.exe"
& $portablePython $getPip --disable-pip-version-check --no-cache-dir
if ($LASTEXITCODE -ne 0) { throw "pip bootstrap failed with exit code $LASTEXITCODE." }

Write-Host "Installing O.R.S.I dependencies inside the portable folder..."
& $portablePython -m pip install --disable-pip-version-check --no-cache-dir -r (Join-Path $projectRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Base dependency installation failed with exit code $LASTEXITCODE." }

$inferenceRequirements = if ($Backend -eq "cuda") {
    Join-Path $projectRoot "requirements-inference-cuda.txt"
} else {
    Join-Path $projectRoot "requirements-inference-cpu.txt"
}
& $portablePython -m pip install --disable-pip-version-check --upgrade --force-reinstall --no-cache-dir -r $inferenceRequirements
if ($LASTEXITCODE -ne 0) { throw "Inference dependency installation failed with exit code $LASTEXITCODE." }

Write-Host "Packaging the pinned native tool-call server..."
& (Join-Path $PSScriptRoot "build-llama-server.ps1") -Backend $Backend
if ($LASTEXITCODE -ne 0) { throw "llama-server packaging failed with exit code $LASTEXITCODE." }

Write-Host "Verifying the portable runtime..."
if ($Backend -eq "cuda") {
    $cudaBin = Join-Path $pythonRoot "Lib\site-packages\nvidia\cu13\bin\x86_64"
    $env:PATH = "$cudaBin;$env:PATH"
}
& $portablePython -c "import sys; import PySide6, pydantic; from app.inference.llama_backend import _configure_portable_cuda_dlls; _configure_portable_cuda_dlls(); from llama_cpp import llama_cpp; print('Python:', sys.version.split()[0]); print('GPU offload:', llama_cpp.llama_supports_gpu_offload())"
if ($LASTEXITCODE -ne 0) { throw "Portable runtime verification failed with exit code $LASTEXITCODE." }

Set-Content -LiteralPath (Join-Path $runtimeRoot "READY.txt") -Encoding UTF8 -Value @"
O.R.S.I portable runtime
Python: 3.12.10 x64
Inference backend: $Backend
Native tool-call server: llama.cpp b9976 (e3546c794)
Created: $([DateTimeOffset]::Now.ToString("O"))
"@

$expectedDownloads = [System.IO.Path]::GetFullPath($downloadsRoot)
$resolvedDownloads = (Resolve-Path -LiteralPath $downloadsRoot).Path
if ($resolvedDownloads -ne $expectedDownloads) {
    throw "Unexpected download-cache cleanup target: $resolvedDownloads"
}
if (-not $resolvedDownloads.StartsWith($runtimeRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Download-cache cleanup target is outside the portable runtime: $resolvedDownloads"
}
$downloadsItem = Get-Item -LiteralPath $resolvedDownloads -Force
if ($downloadsItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
    throw "Download-cache cleanup target is a reparse point: $resolvedDownloads"
}
Remove-Item -LiteralPath $resolvedDownloads -Recurse -Force

Write-Host ""
Write-Host "Portable runtime is ready. Double-click ORSI.cmd to start the application."
