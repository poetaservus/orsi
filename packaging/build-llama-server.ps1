param(
    [ValidateSet("cuda", "cpu")]
    [string]$Backend = "cuda"
)

$ErrorActionPreference = "Stop"
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$runtimeRoot = Join-Path $projectRoot "runtime"
$serverRoot = Join-Path $runtimeRoot "llama-server"
$workRoot = Join-Path $runtimeRoot ".llama-server-b9976-build"
$build = "b9976"
$commit = "e3546c794"

if (-not (Test-Path -LiteralPath $runtimeRoot -PathType Container)) {
    throw "The portable runtime directory is missing: $runtimeRoot"
}
if (Test-Path -LiteralPath $serverRoot) {
    throw "A packaged llama-server already exists at $serverRoot. It was not changed."
}
if (Test-Path -LiteralPath $workRoot) {
    throw "The llama-server staging directory already exists: $workRoot"
}

if ($Backend -eq "cuda") {
    $archiveName = "llama-b9976-bin-win-cuda-13.3-x64.zip"
    $archiveSha256 = "6dbe0c9854632af2e7b4bf7f3a39a8f1a7f13a8cadbce917cfba99e34347b1ee"
} else {
    $archiveName = "llama-b9976-bin-win-cpu-x64.zip"
    $archiveSha256 = "8eee04969ae12a5f2e949b2bce571b83b5e81268fdec78657f9aa617acd9d7b6"
}
$archiveUrl = "https://github.com/ggml-org/llama.cpp/releases/download/$build/$archiveName"
$archivePath = Join-Path $workRoot $archiveName
$extractRoot = Join-Path $workRoot "extract"
$packageRoot = Join-Path $workRoot "package"

function Remove-VerifiedWorkRoot {
    if (-not (Test-Path -LiteralPath $workRoot)) {
        return
    }
    $resolvedRuntime = (Resolve-Path -LiteralPath $runtimeRoot).Path
    $resolvedWork = (Resolve-Path -LiteralPath $workRoot).Path
    $expectedWork = [System.IO.Path]::GetFullPath($workRoot)
    if ($resolvedWork -ne $expectedWork) {
        throw "Unexpected llama-server cleanup target: $resolvedWork"
    }
    if (-not $resolvedWork.StartsWith(
        $resolvedRuntime + [System.IO.Path]::DirectorySeparatorChar,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "The llama-server cleanup target is outside the portable runtime: $resolvedWork"
    }
    $item = Get-Item -LiteralPath $resolvedWork -Force
    if (-not $item.PSIsContainer) {
        throw "The llama-server cleanup target is not a directory: $resolvedWork"
    }
    if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
        throw "The llama-server cleanup target is a reparse point: $resolvedWork"
    }
    Remove-Item -LiteralPath $resolvedWork -Recurse -Force -ErrorAction Stop
}

try {
    New-Item -ItemType Directory -Path $workRoot -ErrorAction Stop | Out-Null
    New-Item -ItemType Directory -Path $extractRoot -ErrorAction Stop | Out-Null
    New-Item -ItemType Directory -Path $packageRoot -ErrorAction Stop | Out-Null

    Write-Host "Downloading pinned llama.cpp $build server ($Backend)..."
    Invoke-WebRequest -Uri $archiveUrl -OutFile $archivePath -UseBasicParsing
    $actualHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $archiveSha256) {
        throw "The pinned llama-server archive checksum did not match."
    }
    Expand-Archive -LiteralPath $archivePath -DestinationPath $extractRoot

    $requiredFiles = @(
        "llama-server.exe",
        "llama-server-impl.dll",
        "llama-common.dll",
        "llama.dll",
        "mtmd.dll",
        "ggml.dll",
        "ggml-base.dll",
        "ggml-rpc.dll",
        "libomp140.x86_64.dll"
    )
    if ($Backend -eq "cuda") {
        $requiredFiles += "ggml-cuda.dll"
    }
    foreach ($name in $requiredFiles) {
        $source = Join-Path $extractRoot $name
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
            throw "The pinned llama-server archive is missing required file: $name"
        }
        Copy-Item -LiteralPath $source -Destination (Join-Path $packageRoot $name)
    }

    $cpuBackends = @(Get-ChildItem -LiteralPath $extractRoot -File -Filter "ggml-cpu-*.dll")
    if (-not $cpuBackends) {
        throw "The pinned llama-server archive contains no CPU fallback backend."
    }
    foreach ($backendFile in $cpuBackends) {
        Copy-Item -LiteralPath $backendFile.FullName -Destination $packageRoot
    }

    if ($Backend -eq "cuda") {
        $cudaBin = Join-Path $runtimeRoot "python\Lib\site-packages\nvidia\cu13\bin\x86_64"
        foreach ($name in @("cudart64_13.dll", "cublas64_13.dll", "cublasLt64_13.dll")) {
            if (-not (Test-Path -LiteralPath (Join-Path $cudaBin $name) -PathType Leaf)) {
                throw "The portable CUDA runtime is missing required library: $name"
            }
        }
        $previousPath = $env:Path
        try {
            $env:Path = "$packageRoot;$cudaBin;$previousPath"
            $version = (& (Join-Path $packageRoot "llama-server.exe") --version 2>&1 | Out-String)
        } finally {
            $env:Path = $previousPath
        }
    } else {
        $version = (& (Join-Path $packageRoot "llama-server.exe") --version 2>&1 | Out-String)
    }
    if ($LASTEXITCODE -ne 0 -or $version -notmatch "version:\s+9976\s+\(e3546c794\)") {
        throw "The packaged llama-server did not report the pinned build identity."
    }

    Set-Content -LiteralPath (Join-Path $packageRoot "BUILD.txt") -Encoding UTF8 -Value @"
O.R.S.I native tool-call server
llama.cpp build: $build
llama.cpp commit: $commit
Backend: $Backend
Archive: $archiveName
Archive SHA-256: $archiveSha256
"@
    Move-Item -LiteralPath $packageRoot -Destination $serverRoot -ErrorAction Stop
    Write-Host "Packaged pinned llama-server at $serverRoot"
} finally {
    Remove-VerifiedWorkRoot
}
